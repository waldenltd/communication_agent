"""
Level 2 Agent - Communication Agent

A goal-oriented autonomous system that uses ReAct (Reason + Act) loops
to perceive state changes, reason over outcomes, and self-correct.

Architecture Layers:
1. Persona & Reasoning Core - System prompts and ReAct engine
2. Action Module - Tool registry with JSON schema interfaces
3. Persistence Layer - Session state and context ledger
4. Control Loop - Sleep/Wake orchestration

Usage:
    from src.agent import get_orchestrator, start_orchestrator, stop_orchestrator

    # Start the agent orchestrator
    start_orchestrator()

    # Create an agent job
    orchestrator = get_orchestrator()
    job_id = orchestrator.create_agent_job(
        tenant_id="tenant-123",
        job_type="communication",
        goal="Process pending communication queue items",
    )

    # Stop gracefully
    stop_orchestrator()
"""

# Lazy imports to avoid circular dependencies
def get_orchestrator():
    """Get or create the global orchestrator instance."""
    from .orchestrator import get_orchestrator as _get
    return _get()


def start_orchestrator():
    """Start the global orchestrator."""
    from .orchestrator import start_orchestrator as _start
    _start()


def stop_orchestrator():
    """Stop the global orchestrator."""
    from .orchestrator import stop_orchestrator as _stop
    _stop()


__all__ = [
    'get_orchestrator',
    'start_orchestrator',
    'stop_orchestrator',
]
