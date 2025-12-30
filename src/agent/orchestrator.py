"""
Agent Orchestrator

The control loop that manages Sleep/Wake cycles for the Level 2 Agent.
This is the "wrapper" that handles the lifecycle of agent execution.

Layer 4 of the 4-Layer Stack: Control Loop
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Callable

from src.config import POLL_INTERVAL_MS, MAX_CONCURRENT_JOBS
from src.logger import info, error, debug, warn

from .context_manager import ContextManager, SessionState, ContextLedger
from .react_engine import ReActEngine, create_react_engine
from .persona.communication import CommunicationAgentPersona, SchedulerAgentPersona
from .tools.registry import ToolRegistry, get_registry
from .tools.perception import register_perception_tools
from .tools.communication import register_communication_tools
from .tools.processing import register_processing_tools
from .tools.persistence import register_persistence_tools


class AgentOrchestrator:
    """
    The Agent Orchestrator manages the execution lifecycle of autonomous agents.

    Responsibilities:
    - Sleep/Wake cycle management
    - Job claiming and dispatching
    - Session hydration and persistence
    - Error handling and recovery
    - Health monitoring
    """

    def __init__(
        self,
        cycle_duration_seconds: int = 600,  # 10 minutes
        poll_interval_ms: int = None,
        max_concurrent_jobs: int = None,
    ):
        self.cycle_duration = cycle_duration_seconds
        self.poll_interval = (poll_interval_ms or POLL_INTERVAL_MS) / 1000.0
        self.max_concurrent = max_concurrent_jobs or MAX_CONCURRENT_JOBS

        # Components
        self.context_manager = ContextManager()
        self.tool_registry = self._initialize_tools()
        self.personas = self._initialize_personas()

        # Runtime state
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._active_jobs: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

        # Metrics
        self._cycles_completed = 0
        self._jobs_processed = 0
        self._jobs_failed = 0

    def _initialize_tools(self) -> ToolRegistry:
        """Initialize the tool registry with all available tools."""
        registry = get_registry()

        # Register all tool categories
        register_perception_tools(registry)
        register_communication_tools(registry)
        register_processing_tools(registry)
        register_persistence_tools(registry)

        info(f"Tool registry initialized",
             tool_count=len(registry.list_tools()))

        return registry

    def _initialize_personas(self) -> dict:
        """Initialize available agent personas."""
        return {
            "communication": CommunicationAgentPersona(),
            "scheduler": SchedulerAgentPersona(),
        }

    def start(self) -> None:
        """Start the orchestrator in a background thread."""
        if self._running:
            warn("Orchestrator already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        info("Agent orchestrator started",
             cycle_duration=self.cycle_duration,
             poll_interval=self.poll_interval)

    def stop(self) -> None:
        """Stop the orchestrator gracefully."""
        if not self._running:
            return

        info("Stopping agent orchestrator...")
        self._running = False

        # Wait for active jobs to complete (with timeout)
        deadline = time.time() + 30  # 30 second grace period
        while self._active_jobs and time.time() < deadline:
            time.sleep(0.5)

        if self._active_jobs:
            warn(f"Force stopping with {len(self._active_jobs)} active jobs")

        if self._thread:
            self._thread.join(timeout=5)

        info("Agent orchestrator stopped",
             cycles=self._cycles_completed,
             jobs_processed=self._jobs_processed,
             jobs_failed=self._jobs_failed)

    def _run_loop(self) -> None:
        """Main orchestrator loop - manages Sleep/Wake cycles."""
        while self._running:
            cycle_start = time.time()

            try:
                self._run_cycle()
                self._cycles_completed += 1
            except Exception as e:
                error("Cycle failed", err=e)

            # Sleep until next cycle
            elapsed = time.time() - cycle_start
            sleep_time = max(0, self.poll_interval - elapsed)

            if sleep_time > 0:
                time.sleep(sleep_time)

    def _run_cycle(self) -> None:
        """
        Execute a single processing cycle.

        This is the "Wake" phase where we:
        1. Claim pending jobs
        2. Hydrate context
        3. Run reasoning loops
        4. Persist state
        5. Return to "Sleep"
        """
        # Check capacity
        with self._lock:
            available_slots = self.max_concurrent - len(self._active_jobs)

        if available_slots <= 0:
            debug("No available slots, skipping cycle")
            return

        # Claim pending jobs
        jobs = self.context_manager.claim_pending_jobs(limit=available_slots)

        if not jobs:
            debug("No pending jobs")
            return

        debug(f"Claimed {len(jobs)} jobs for processing")

        # Process each job
        for job_row in jobs:
            self._spawn_job_worker(job_row)

    def _spawn_job_worker(self, job_row: dict) -> None:
        """Spawn a worker thread for a job."""
        job_id = str(job_row["id"])

        def worker():
            try:
                self._process_job(job_row)
                self._jobs_processed += 1
            except Exception as e:
                error(f"Job worker failed", job_id=job_id, err=e)
                self._jobs_failed += 1
                self.context_manager.mark_failed(job_id, str(e))
            finally:
                with self._lock:
                    self._active_jobs.pop(job_id, None)

        thread = threading.Thread(target=worker, daemon=True)

        with self._lock:
            self._active_jobs[job_id] = thread

        thread.start()

    def _process_job(self, job_row: dict) -> None:
        """
        Process a single agent job through the ReAct loop.

        Phases:
        1. HYDRATE - Load context from persistence
        2. PERCEIVE/PLAN/EXECUTE - Run ReAct engine
        3. PERSIST - Save state for next cycle
        """
        job_id = str(job_row["id"])
        tenant_id = job_row["tenant_id"]
        job_type = job_row["job_type"]
        goal = job_row["goal"]
        max_iterations = job_row.get("max_iterations", 20)

        info(f"Processing agent job",
             job_id=job_id,
             tenant_id=tenant_id,
             job_type=job_type)

        # Phase 1: HYDRATE
        session, ledger = self.context_manager.hydrate_from_job(job_row)

        # Select persona
        persona = self.personas.get(job_type, self.personas["communication"])

        # Create engine
        engine = create_react_engine(
            persona=persona,
            tool_registry=self.tool_registry,
            max_iterations=max_iterations,
        )

        # Phase 2-6: Run ReAct Loop
        cycle_start = time.time()
        max_cycle_time = self.cycle_duration * 0.8  # Leave 20% buffer

        try:
            success, result = engine.run(
                goal=goal,
                session=session,
                ledger=ledger,
                tenant_id=tenant_id,
            )

            # Phase 7: PERSIST
            self.context_manager.save_session(session)
            self.context_manager.save_context(ledger)

            elapsed = time.time() - cycle_start

            if success:
                self.context_manager.mark_complete(job_id, result)
                info(f"Agent job completed",
                     job_id=job_id,
                     elapsed_seconds=round(elapsed, 2))
            else:
                # Check if we need to reschedule or wait for human
                if "human" in result.lower():
                    self.context_manager.mark_waiting_human(job_id, result)
                else:
                    # Reschedule for retry
                    self.context_manager.reschedule_job(
                        job_id,
                        delay_seconds=300,  # 5 minutes
                        ledger=ledger,
                    )
                    info(f"Agent job rescheduled",
                         job_id=job_id,
                         reason=result[:100])

        except Exception as e:
            error(f"ReAct loop failed", job_id=job_id, err=e)

            # Save what we have
            self.context_manager.save_session(session)
            ledger.context_summary = f"Error: {str(e)}"
            self.context_manager.save_context(ledger)

            # Reschedule with backoff
            self.context_manager.reschedule_job(
                job_id,
                delay_seconds=600,  # 10 minutes
                ledger=ledger,
            )

    def create_agent_job(
        self,
        tenant_id: str,
        job_type: str,
        goal: str,
        checklist: list[str] = None,
        source_job_id: int = None,
        source_reference: str = None,
    ) -> str:
        """
        Create a new agent job for processing.

        This is the entry point for scheduling autonomous work.
        """
        job_id = self.context_manager.create_job(
            tenant_id=tenant_id,
            job_type=job_type,
            goal=goal,
            checklist=checklist,
            source_job_id=source_job_id,
            source_reference=source_reference,
        )

        info(f"Created agent job",
             job_id=job_id,
             tenant_id=tenant_id,
             job_type=job_type,
             goal=goal[:100])

        return job_id

    def get_status(self) -> dict:
        """Get orchestrator status and metrics."""
        with self._lock:
            active_count = len(self._active_jobs)

        return {
            "running": self._running,
            "active_jobs": active_count,
            "max_concurrent": self.max_concurrent,
            "cycles_completed": self._cycles_completed,
            "jobs_processed": self._jobs_processed,
            "jobs_failed": self._jobs_failed,
            "cycle_duration_seconds": self.cycle_duration,
        }


# Global orchestrator instance
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


def start_orchestrator() -> None:
    """Start the global orchestrator."""
    get_orchestrator().start()


def stop_orchestrator() -> None:
    """Stop the global orchestrator."""
    if _orchestrator:
        _orchestrator.stop()
