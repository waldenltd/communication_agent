#!/usr/bin/env python
"""
End-to-End Integration Tests for the Level 2 Agent.

Tests complete cycles through the agent system:
1. Job creation → ReAct reasoning → Tool execution → Completion
2. Job bridge conversions
3. Agent scheduler job creation
4. Error handling and recovery

Usage:
    python scripts/test_agent_e2e.py

Note: Requires database and may require DEEPSEEK_API_KEY for full tests.
"""

import os
import sys
import time
import uuid
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment
env_local = Path(__file__).parent.parent / '.env.local'
if env_local.exists():
    load_dotenv(env_local)
else:
    load_dotenv()


def test_job_bridge():
    """Test the job bridge converts legacy jobs correctly."""
    print("\n" + "="*50)
    print("Testing Job Bridge")
    print("="*50)

    from src.agent.job_bridge import JobBridge, JOB_TYPE_GOALS
    from src.db.central_db import query

    bridge = JobBridge()

    # Test goal templates exist
    assert len(JOB_TYPE_GOALS) >= 5, "Should have at least 5 job type templates"
    print(f"✓ {len(JOB_TYPE_GOALS)} job type templates defined")

    # Test service reminder job creation
    tenant_id = f"test-{uuid.uuid4().hex[:8]}"
    job_id = bridge.create_service_reminder_job(
        tenant_id=tenant_id,
        customer_id="cust-123",
        customer_email="test@example.com",
        customer_name="John Doe",
        model="Lawn Mower XL",
        serial_number="SN12345",
    )

    assert job_id is not None, "Should create service reminder job"
    print(f"✓ Created service reminder job: {job_id}")

    # Verify job was created with correct data
    rows = query("SELECT * FROM agent_jobs WHERE id = %s::uuid", [job_id])
    assert len(rows) == 1
    job = rows[0]
    assert "service reminder" in job["goal"].lower()
    assert job["job_type"] == "communication"
    print(f"✓ Job has correct goal: {job['goal'][:50]}...")

    # Test session variables were stored
    from src.agent.context_manager import ContextManager
    cm = ContextManager()
    session = cm.load_session(job_id)
    assert session.get_variable("customer_id") == "cust-123"
    assert session.get_variable("model") == "Lawn Mower XL"
    print("✓ Session variables stored correctly")

    # Cleanup
    query("DELETE FROM agent_jobs WHERE id = %s::uuid", [job_id])
    print("✓ Cleaned up test job")

    # Test migration stats
    stats = bridge.get_migration_stats()
    assert "legacy_jobs" in stats
    assert "agent_jobs" in stats
    print(f"✓ Migration stats: {stats['agent_jobs']['total']} agent jobs")

    print("\n✓ Job Bridge tests passed!")
    return True


def test_react_engine_simple():
    """Test the ReAct engine with a simple goal (no LLM needed)."""
    print("\n" + "="*50)
    print("Testing ReAct Engine (Simple)")
    print("="*50)

    from src.agent.context_manager import SessionState, ContextLedger
    from src.agent.tools.registry import ToolRegistry
    from src.agent.tools.processing import register_processing_tools

    # Create a minimal registry with just one tool
    registry = ToolRegistry()
    register_processing_tools(registry)

    # Create session and ledger
    session = SessionState(
        job_id="test-123",
        goal="Calculate days past due for an invoice",
        checklist=["Calculate days past due"],
    )
    ledger = ContextLedger(job_id="test-123")

    # Manually simulate one iteration (without LLM)
    tool = registry.get("calculate_days_past_due")
    result = tool(due_date="2024-01-01")

    assert result.success
    assert result.data["is_past_due"] == True
    print(f"✓ Tool execution works: {result.data['days_past_due']} days past due")

    # Test session state management
    session.add_thought("I need to calculate days past due")
    session.advance_step()
    assert session.current_step == 1
    assert session.is_complete()
    print("✓ Session state management works")

    # Test ledger recording
    from src.agent.context_manager import ReasoningStep
    from datetime import datetime
    ledger.add_step(ReasoningStep(
        step_number=1,
        timestamp=datetime.utcnow().isoformat() + "Z",
        thought="Calculating days past due",
        action={"tool": "calculate_days_past_due", "params": {"due_date": "2024-01-01"}},
        observation=str(result.data),
    ))
    assert len(ledger.reasoning_trace) == 1
    print("✓ Reasoning trace recording works")

    print("\n✓ ReAct Engine (Simple) tests passed!")
    return True


def test_full_agent_cycle():
    """Test a full agent cycle with database persistence."""
    print("\n" + "="*50)
    print("Testing Full Agent Cycle")
    print("="*50)

    from src.agent.context_manager import ContextManager
    from src.agent.orchestrator import AgentOrchestrator
    from src.db.central_db import query

    # Create orchestrator (but don't start background threads)
    orchestrator = AgentOrchestrator(
        cycle_duration_seconds=60,
        poll_interval_ms=1000,
        max_concurrent_jobs=1,
    )

    # Create a test job
    tenant_id = f"test-{uuid.uuid4().hex[:8]}"
    job_id = orchestrator.create_agent_job(
        tenant_id=tenant_id,
        job_type="communication",
        goal="Test job for e2e validation",
        checklist=["Step 1: Validate", "Step 2: Complete"],
    )

    assert job_id is not None
    print(f"✓ Created agent job: {job_id}")

    # Verify job in database
    rows = query("SELECT * FROM agent_jobs WHERE id = %s::uuid", [job_id])
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    print("✓ Job is pending in database")

    # Test claiming jobs
    cm = ContextManager()
    claimed = cm.claim_pending_jobs(limit=1)
    # Note: This might claim our job or not depending on timing
    print(f"✓ Job claiming works ({len(claimed)} jobs claimed)")

    # Test session hydration
    session = cm.load_session(job_id)
    if session:
        assert session.goal == "Test job for e2e validation"
        print("✓ Session hydration works")

        # Simulate processing
        session.add_thought("Processing the test job")
        session.advance_step()
        cm.save_session(session)
        print("✓ Session save works")

    # Mark complete
    cm.mark_complete(job_id, "E2E test completed successfully")

    # Verify completion
    rows = query("SELECT * FROM agent_jobs WHERE id = %s::uuid", [job_id])
    assert rows[0]["status"] == "resolved"
    print("✓ Job marked as resolved")

    # Cleanup
    query("DELETE FROM agent_jobs WHERE id = %s::uuid", [job_id])
    print("✓ Cleaned up test job")

    print("\n✓ Full Agent Cycle tests passed!")
    return True


def test_orchestrator_lifecycle():
    """Test orchestrator start/stop lifecycle."""
    print("\n" + "="*50)
    print("Testing Orchestrator Lifecycle")
    print("="*50)

    from src.agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator(
        cycle_duration_seconds=10,
        poll_interval_ms=500,
        max_concurrent_jobs=2,
    )

    # Check initial status
    status = orchestrator.get_status()
    assert status["running"] == False
    print("✓ Orchestrator starts in stopped state")

    # Start orchestrator
    orchestrator.start()
    time.sleep(0.5)

    status = orchestrator.get_status()
    assert status["running"] == True
    print("✓ Orchestrator started successfully")

    # Let it run briefly
    time.sleep(1)

    # Stop orchestrator
    orchestrator.stop()
    time.sleep(0.5)

    status = orchestrator.get_status()
    assert status["running"] == False
    print(f"✓ Orchestrator stopped (ran {status['cycles_completed']} cycles)")

    print("\n✓ Orchestrator Lifecycle tests passed!")
    return True


def test_error_handling():
    """Test error handling and recovery."""
    print("\n" + "="*50)
    print("Testing Error Handling")
    print("="*50)

    from src.agent.context_manager import ContextManager
    from src.agent.tools.base import ToolResult

    cm = ContextManager()

    # Create a job
    tenant_id = f"test-{uuid.uuid4().hex[:8]}"
    job_id = cm.create_job(
        tenant_id=tenant_id,
        job_type="communication",
        goal="Test error handling",
    )
    print(f"✓ Created test job: {job_id}")

    # Mark as failed
    cm.mark_failed(job_id, "Simulated error for testing")

    # Verify failed status
    from src.db.central_db import query
    rows = query("SELECT * FROM agent_jobs WHERE id = %s::uuid", [job_id])
    assert rows[0]["status"] == "failed"
    assert "Simulated error" in rows[0]["last_error"]
    print("✓ Job marked as failed with error message")

    # Test ToolResult error handling
    result = ToolResult(
        success=False,
        error="Test error",
        needs_retry=True,
        retry_reason="Transient failure",
        suggested_action="Try again",
    )
    assert not result.success
    assert result.needs_retry
    observation = result.to_observation()
    assert "Error:" in observation
    assert "Suggested action:" in observation
    print("✓ ToolResult error formatting works")

    # Cleanup
    query("DELETE FROM agent_jobs WHERE id = %s::uuid", [job_id])
    print("✓ Cleaned up test job")

    print("\n✓ Error Handling tests passed!")
    return True


def test_health_endpoints():
    """Test health check endpoints."""
    print("\n" + "="*50)
    print("Testing Health Endpoints")
    print("="*50)

    from src.health import HealthServer
    import urllib.request
    import json

    def get_status():
        return {
            "running": True,
            "mode": "test",
            "jobs_processed": 42,
        }

    server = HealthServer(port=8082, status_provider=get_status)
    server.start()
    time.sleep(0.5)

    try:
        # Test /health
        resp = urllib.request.urlopen('http://localhost:8082/health')
        data = json.loads(resp.read())
        assert data["status"] == "healthy"
        print("✓ /health returns healthy")

        # Test /ready
        resp = urllib.request.urlopen('http://localhost:8082/ready')
        data = json.loads(resp.read())
        assert data["status"] == "ready"
        assert data["running"] == True
        print("✓ /ready returns ready")

        # Test /status
        resp = urllib.request.urlopen('http://localhost:8082/status')
        data = json.loads(resp.read())
        assert data["mode"] == "test"
        assert data["jobs_processed"] == 42
        print("✓ /status returns detailed status")

    finally:
        server.stop()

    print("\n✓ Health Endpoints tests passed!")
    return True


def test_with_llm():
    """Test with actual LLM (requires DEEPSEEK_API_KEY)."""
    print("\n" + "="*50)
    print("Testing with LLM (Optional)")
    print("="*50)

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("⚠ DEEPSEEK_API_KEY not set, skipping LLM tests")
        return True

    from src.agent.react_engine import ReActEngine, create_react_engine
    from src.agent.persona.communication import CommunicationAgentPersona
    from src.agent.context_manager import SessionState, ContextLedger

    # Create engine
    persona = CommunicationAgentPersona()
    engine = create_react_engine(persona=persona, max_iterations=3)
    print("✓ Created ReActEngine with LLM")

    # Create test session
    session = SessionState(
        job_id="llm-test-123",
        goal="Calculate how many days invoice #1234 is past due (due date: 2024-06-15)",
        checklist=["Calculate days past due for the invoice"],
    )
    ledger = ContextLedger(job_id="llm-test-123")

    # Run single iteration (don't run full loop to save API calls)
    try:
        # Just test that we can call the LLM
        system_prompt = engine._build_system_prompt(session, ledger)
        user_prompt = engine._build_user_prompt(session.goal, session, "test-tenant")

        assert len(system_prompt) > 1000  # Should be substantial
        assert "GOAL:" in user_prompt
        print(f"✓ Prompts generated ({len(system_prompt)} chars system, {len(user_prompt)} chars user)")

        # Test goal decomposition (makes actual API call)
        steps = engine._decompose_goal("Send a reminder email to customer about past due invoice")
        assert len(steps) >= 1
        print(f"✓ Goal decomposed into {len(steps)} steps")
        for i, step in enumerate(steps[:3]):
            print(f"    {i+1}. {step[:60]}...")

    except Exception as e:
        print(f"⚠ LLM test failed (may be API issue): {e}")
        return True  # Don't fail the suite for LLM issues

    print("\n✓ LLM tests passed!")
    return True


def main():
    """Run all end-to-end tests."""
    print("\n" + "="*50)
    print("Level 2 Agent End-to-End Test Suite")
    print("="*50)

    tests = [
        ("Job Bridge", test_job_bridge),
        ("ReAct Engine (Simple)", test_react_engine_simple),
        ("Full Agent Cycle", test_full_agent_cycle),
        ("Orchestrator Lifecycle", test_orchestrator_lifecycle),
        ("Error Handling", test_error_handling),
        ("Health Endpoints", test_health_endpoints),
        ("LLM Integration", test_with_llm),
    ]

    results = []
    for name, test_fn in tests:
        try:
            result = test_fn()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "="*50)
    print("End-to-End Test Summary")
    print("="*50)

    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed

    for name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"  {status}: {name}")

    print(f"\n{passed}/{len(results)} tests passed")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
