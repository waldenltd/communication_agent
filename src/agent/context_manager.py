"""
Context Manager

Manages session state (short-term) and context ledger (long-term) memory
for the Level 2 Agent.

Layer 3 of the 4-Layer Stack: Persistence Layer
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import json
import uuid

from src.db.central_db import query, execute
from src.logger import info, error, debug


@dataclass
class ReasoningStep:
    """A single step in the ReAct reasoning trace."""
    step_number: int
    timestamp: str
    thought: str
    action: Optional[dict] = None
    observation: Optional[str] = None
    next_thought: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "step": self.step_number,
            "timestamp": self.timestamp,
            "thought": self.thought,
            "action": self.action,
            "observation": self.observation,
            "next_thought": self.next_thought,
        }


@dataclass
class SessionState:
    """
    Short-term memory for the current agent session.

    Tracks the immediate context needed for the reasoning loop.
    """
    job_id: str
    goal: str
    checklist: list[str] = field(default_factory=list)
    current_step: int = 0
    last_thoughts: deque = field(default_factory=lambda: deque(maxlen=10))
    variables: dict = field(default_factory=dict)
    iteration_count: int = 0

    def add_thought(self, thought: str) -> None:
        """Add a thought to the rolling window."""
        self.last_thoughts.append({
            "thought": thought,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })

    def get_recent_thoughts(self, n: int = 5) -> list[dict]:
        """Get the n most recent thoughts."""
        return list(self.last_thoughts)[-n:]

    def advance_step(self) -> None:
        """Move to the next step in the checklist."""
        self.current_step += 1

    def get_current_task(self) -> Optional[str]:
        """Get the current task from the checklist."""
        if 0 <= self.current_step < len(self.checklist):
            return self.checklist[self.current_step]
        return None

    def is_complete(self) -> bool:
        """Check if all checklist items are done."""
        return self.current_step >= len(self.checklist)

    def set_variable(self, key: str, value: Any) -> None:
        """Store a variable in the session scratchpad."""
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Retrieve a variable from the session scratchpad."""
        return self.variables.get(key, default)

    def to_dict(self) -> dict:
        """Serialize session state for persistence."""
        return {
            "job_id": self.job_id,
            "goal": self.goal,
            "checklist": self.checklist,
            "current_step": self.current_step,
            "last_thoughts": list(self.last_thoughts),
            "variables": self.variables,
            "iteration_count": self.iteration_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        """Deserialize session state from persistence."""
        state = cls(
            job_id=data["job_id"],
            goal=data["goal"],
            checklist=data.get("checklist", []),
            current_step=data.get("current_step", 0),
            variables=data.get("variables", {}),
            iteration_count=data.get("iteration_count", 0),
        )
        for thought in data.get("last_thoughts", []):
            state.last_thoughts.append(thought)
        return state


@dataclass
class ContextLedger:
    """
    Long-term memory for agent context across sessions.

    Stores reasoning traces and summaries for hydrating future sessions.
    """
    job_id: str
    context_summary: Optional[str] = None
    reasoning_trace: list[ReasoningStep] = field(default_factory=list)

    def add_step(self, step: ReasoningStep) -> None:
        """Add a reasoning step to the trace."""
        self.reasoning_trace.append(step)

    def get_trace_for_prompt(self, max_steps: int = 5) -> str:
        """Format recent trace steps for inclusion in prompt."""
        recent = self.reasoning_trace[-max_steps:] if self.reasoning_trace else []
        if not recent:
            return "No previous reasoning steps."

        lines = []
        for step in recent:
            lines.append(f"Step {step.step_number}:")
            lines.append(f"  Thought: {step.thought}")
            if step.action:
                lines.append(f"  Action: {step.action.get('tool', 'unknown')}")
            if step.observation:
                obs = step.observation[:200] + "..." if len(step.observation) > 200 else step.observation
                lines.append(f"  Observation: {obs}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize ledger for persistence."""
        return {
            "job_id": self.job_id,
            "context_summary": self.context_summary,
            "reasoning_trace": [s.to_dict() for s in self.reasoning_trace],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextLedger":
        """Deserialize ledger from persistence."""
        ledger = cls(
            job_id=data["job_id"],
            context_summary=data.get("context_summary"),
        )
        for step_data in data.get("reasoning_trace", []):
            ledger.reasoning_trace.append(ReasoningStep(
                step_number=step_data["step"],
                timestamp=step_data["timestamp"],
                thought=step_data["thought"],
                action=step_data.get("action"),
                observation=step_data.get("observation"),
                next_thought=step_data.get("next_thought"),
            ))
        return ledger


class ContextManager:
    """
    Manages persistence of agent state and context.

    Handles:
    - Creating new agent jobs
    - Loading/saving session state
    - Loading/saving context ledger
    - Generating context summaries
    """

    # SQL Queries
    CREATE_JOB = """
        INSERT INTO agent_jobs (
            tenant_id, job_type, goal, status, checklist,
            source_job_id, source_reference, max_iterations
        ) VALUES (
            %(tenant_id)s, %(job_type)s, %(goal)s, 'pending', %(checklist)s,
            %(source_job_id)s, %(source_reference)s, %(max_iterations)s
        )
        RETURNING id
    """

    LOAD_JOB = """
        SELECT id, tenant_id, job_type, goal, status, current_step, checklist,
               context_summary, reasoning_trace, session_state, last_thoughts,
               retry_count, max_retries, max_iterations, iteration_count,
               last_error, process_after, source_job_id, waiting_for_human,
               human_prompt, human_response
        FROM agent_jobs
        WHERE id = %(job_id)s
    """

    CLAIM_PENDING_JOBS = """
        UPDATE agent_jobs
        SET status = 'in_progress', started_at = NOW()
        WHERE id IN (
            SELECT id FROM agent_jobs
            WHERE status = 'pending'
              AND process_after <= NOW()
            ORDER BY process_after
            LIMIT %(limit)s
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, tenant_id, job_type, goal, checklist, context_summary,
                  session_state, last_thoughts, iteration_count, max_iterations
    """

    SAVE_SESSION = """
        UPDATE agent_jobs
        SET current_step = %(current_step)s,
            checklist = %(checklist)s,
            session_state = %(session_state)s,
            last_thoughts = %(last_thoughts)s,
            iteration_count = %(iteration_count)s
        WHERE id = %(job_id)s
    """

    SAVE_CONTEXT = """
        UPDATE agent_jobs
        SET context_summary = %(context_summary)s,
            reasoning_trace = %(reasoning_trace)s
        WHERE id = %(job_id)s
    """

    MARK_COMPLETE = """
        UPDATE agent_jobs
        SET status = 'resolved',
            completed_at = NOW(),
            context_summary = %(context_summary)s
        WHERE id = %(job_id)s
    """

    MARK_FAILED = """
        UPDATE agent_jobs
        SET status = 'failed',
            last_error = %(error)s,
            completed_at = NOW()
        WHERE id = %(job_id)s
    """

    MARK_WAITING_HUMAN = """
        UPDATE agent_jobs
        SET status = 'waiting_human',
            waiting_for_human = TRUE,
            human_prompt = %(prompt)s
        WHERE id = %(job_id)s
    """

    RESCHEDULE_JOB = """
        UPDATE agent_jobs
        SET status = 'pending',
            process_after = %(process_after)s,
            retry_count = retry_count + 1,
            context_summary = %(context_summary)s,
            reasoning_trace = %(reasoning_trace)s
        WHERE id = %(job_id)s
    """

    def create_job(
        self,
        tenant_id: str,
        job_type: str,
        goal: str,
        checklist: list[str] = None,
        source_job_id: int = None,
        source_reference: str = None,
        max_iterations: int = 20,
    ) -> str:
        """Create a new agent job and return its ID."""
        result = query(self.CREATE_JOB, {
            "tenant_id": tenant_id,
            "job_type": job_type,
            "goal": goal,
            "checklist": json.dumps(checklist or []),
            "source_job_id": source_job_id,
            "source_reference": source_reference,
            "max_iterations": max_iterations,
        })

        job_id = str(result[0]["id"])
        info(f"Created agent job: {job_id}",
             tenant_id=tenant_id, job_type=job_type, goal=goal[:100])
        return job_id

    def claim_pending_jobs(self, limit: int = 5) -> list[dict]:
        """
        Claim pending jobs for processing.

        Uses SELECT FOR UPDATE SKIP LOCKED for idempotent claiming.
        """
        jobs = query(self.CLAIM_PENDING_JOBS, {"limit": limit})
        if jobs:
            info(f"Claimed {len(jobs)} agent jobs")
        return jobs

    def load_session(self, job_id: str) -> Optional[SessionState]:
        """Load session state for a job."""
        result = query(self.LOAD_JOB, {"job_id": job_id})
        if not result:
            return None

        row = result[0]
        session_data = row.get("session_state") or {}
        if isinstance(session_data, str):
            session_data = json.loads(session_data)

        checklist = row.get("checklist") or []
        if isinstance(checklist, str):
            checklist = json.loads(checklist)

        last_thoughts = row.get("last_thoughts") or []
        if isinstance(last_thoughts, str):
            last_thoughts = json.loads(last_thoughts)

        state = SessionState(
            job_id=str(row["id"]),
            goal=row["goal"],
            checklist=checklist,
            current_step=row.get("current_step", 0),
            variables=session_data.get("variables", {}),
            iteration_count=row.get("iteration_count", 0),
        )

        for thought in last_thoughts:
            state.last_thoughts.append(thought)

        debug(f"Loaded session for job {job_id}",
              current_step=state.current_step,
              checklist_length=len(state.checklist))

        return state

    def load_context(self, job_id: str) -> Optional[ContextLedger]:
        """Load context ledger for a job."""
        result = query(self.LOAD_JOB, {"job_id": job_id})
        if not result:
            return None

        row = result[0]
        trace_data = row.get("reasoning_trace") or []
        if isinstance(trace_data, str):
            trace_data = json.loads(trace_data)

        ledger = ContextLedger(
            job_id=str(row["id"]),
            context_summary=row.get("context_summary"),
        )

        for step_data in trace_data:
            ledger.reasoning_trace.append(ReasoningStep(
                step_number=step_data.get("step", 0),
                timestamp=step_data.get("timestamp", ""),
                thought=step_data.get("thought", ""),
                action=step_data.get("action"),
                observation=step_data.get("observation"),
                next_thought=step_data.get("next_thought"),
            ))

        return ledger

    def save_session(self, state: SessionState) -> None:
        """Save session state to database."""
        execute(self.SAVE_SESSION, {
            "job_id": state.job_id,
            "current_step": state.current_step,
            "checklist": json.dumps(state.checklist),
            "session_state": json.dumps({"variables": state.variables}),
            "last_thoughts": json.dumps(list(state.last_thoughts)),
            "iteration_count": state.iteration_count,
        })
        debug(f"Saved session for job {state.job_id}")

    def save_context(self, ledger: ContextLedger) -> None:
        """Save context ledger to database."""
        execute(self.SAVE_CONTEXT, {
            "job_id": ledger.job_id,
            "context_summary": ledger.context_summary,
            "reasoning_trace": json.dumps([s.to_dict() for s in ledger.reasoning_trace]),
        })
        debug(f"Saved context for job {ledger.job_id}")

    def mark_complete(self, job_id: str, summary: str = None) -> None:
        """Mark a job as successfully completed."""
        execute(self.MARK_COMPLETE, {
            "job_id": job_id,
            "context_summary": summary or "Job completed successfully.",
        })
        info(f"Agent job completed: {job_id}")

    def mark_failed(self, job_id: str, error_msg: str) -> None:
        """Mark a job as failed."""
        execute(self.MARK_FAILED, {
            "job_id": job_id,
            "error": error_msg,
        })
        error(f"Agent job failed: {job_id}", error=error_msg)

    def mark_waiting_human(self, job_id: str, prompt: str) -> None:
        """Mark a job as waiting for human input."""
        execute(self.MARK_WAITING_HUMAN, {
            "job_id": job_id,
            "prompt": prompt,
        })
        info(f"Agent job waiting for human: {job_id}", prompt=prompt[:100])

    def reschedule_job(
        self,
        job_id: str,
        delay_seconds: int,
        ledger: ContextLedger,
    ) -> None:
        """Reschedule a job for later processing."""
        from datetime import timedelta
        process_after = datetime.utcnow() + timedelta(seconds=delay_seconds)

        execute(self.RESCHEDULE_JOB, {
            "job_id": job_id,
            "process_after": process_after,
            "context_summary": ledger.context_summary,
            "reasoning_trace": json.dumps([s.to_dict() for s in ledger.reasoning_trace]),
        })
        info(f"Rescheduled agent job: {job_id}", delay_seconds=delay_seconds)

    def hydrate_from_job(self, job_row: dict) -> tuple[SessionState, ContextLedger]:
        """
        Hydrate session and context from a claimed job row.

        This is the "boot" phase - loading state for a new cycle.
        """
        job_id = str(job_row["id"])

        # Parse checklist
        checklist = job_row.get("checklist") or []
        if isinstance(checklist, str):
            checklist = json.loads(checklist)

        # Parse session state
        session_data = job_row.get("session_state") or {}
        if isinstance(session_data, str):
            session_data = json.loads(session_data)

        # Parse last thoughts
        last_thoughts = job_row.get("last_thoughts") or []
        if isinstance(last_thoughts, str):
            last_thoughts = json.loads(last_thoughts)

        # Create session state
        state = SessionState(
            job_id=job_id,
            goal=job_row["goal"],
            checklist=checklist,
            current_step=session_data.get("current_step", 0),
            variables=session_data.get("variables", {}),
            iteration_count=job_row.get("iteration_count", 0),
        )
        for thought in last_thoughts:
            state.last_thoughts.append(thought)

        # Create context ledger (start fresh for now, load trace if needed)
        ledger = ContextLedger(
            job_id=job_id,
            context_summary=job_row.get("context_summary"),
        )

        info(f"Hydrated agent job: {job_id}",
             goal=state.goal[:50],
             iteration=state.iteration_count,
             max_iterations=job_row.get("max_iterations", 20))

        return state, ledger
