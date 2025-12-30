#!/usr/bin/env python
"""
Test script for the Level 2 Agent system.

Verifies that tools, personas, and the orchestrator work correctly.

Usage:
    python scripts/test_agent.py
"""

import os
import sys
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


def test_tool_registry():
    """Test that all tools are registered correctly."""
    print("\n" + "="*50)
    print("Testing Tool Registry")
    print("="*50)

    from src.agent.tools.registry import ToolRegistry
    from src.agent.tools.perception import register_perception_tools
    from src.agent.tools.communication import register_communication_tools
    from src.agent.tools.processing import register_processing_tools
    from src.agent.tools.persistence import register_persistence_tools

    registry = ToolRegistry()

    # Register all tools
    register_perception_tools(registry)
    register_communication_tools(registry)
    register_processing_tools(registry)
    register_persistence_tools(registry)

    tools = registry.list_tools()
    print(f"✓ Registered {len(tools)} tools")

    # List tools by category
    from src.agent.tools.base import ToolCategory
    for category in ToolCategory:
        cat_tools = registry.list_tools(category)
        print(f"  - {category.value}: {len(cat_tools)} tools")
        for name in cat_tools:
            tool = registry.get(name)
            print(f"      • {name}: {tool.description[:50]}...")

    # Test JSON schema generation
    schemas = registry.get_all_schemas()
    print(f"\n✓ Generated {len(schemas)} JSON schemas for LLM")

    # Validate schema structure
    for schema in schemas[:3]:
        assert "name" in schema
        assert "description" in schema
        assert "parameters" in schema
        print(f"  - {schema['name']}: valid schema")

    print("\n✓ Tool Registry tests passed!")
    return True


def test_personas():
    """Test that personas generate valid prompts."""
    print("\n" + "="*50)
    print("Testing Agent Personas")
    print("="*50)

    from src.agent.persona.communication import (
        CommunicationAgentPersona,
        SchedulerAgentPersona,
    )

    # Test CommunicationAgentPersona
    comm_persona = CommunicationAgentPersona()
    prompt = comm_persona.get_system_prompt()

    assert "IDENTITY" in prompt
    assert "GOOD TASTE" in prompt
    assert "ReAct" in prompt
    assert "OUTPUT FORMAT" in prompt
    print(f"✓ CommunicationAgentPersona: {len(prompt)} chars")
    print(f"  - Good taste rules: {len(comm_persona.good_taste_rules)}")

    # Test SchedulerAgentPersona
    sched_persona = SchedulerAgentPersona()
    prompt = sched_persona.get_system_prompt()
    assert "Scheduler Agent" in prompt
    print(f"✓ SchedulerAgentPersona: {len(prompt)} chars")

    # Test checklist prompt generation
    checklist = ["Step 1: Check queue", "Step 2: Send emails", "Step 3: Update status"]
    checklist_prompt = comm_persona.get_checklist_prompt(checklist, 1)
    assert ">>>" in checklist_prompt  # Current step marker
    assert "[DONE]" in checklist_prompt  # Completed step
    assert "[TODO]" in checklist_prompt  # Current step
    print(f"✓ Checklist prompt generation works")

    print("\n✓ Persona tests passed!")
    return True


def test_context_manager():
    """Test the context manager for state persistence."""
    print("\n" + "="*50)
    print("Testing Context Manager")
    print("="*50)

    from src.agent.context_manager import (
        ContextManager,
        SessionState,
        ContextLedger,
        ReasoningStep,
    )

    # Test SessionState
    session = SessionState(
        job_id="test-123",
        goal="Test goal",
        checklist=["Step 1", "Step 2", "Step 3"],
    )

    session.add_thought("First thought")
    session.add_thought("Second thought")
    assert len(session.get_recent_thoughts()) == 2
    print("✓ SessionState thought tracking works")

    session.advance_step()
    assert session.current_step == 1
    assert session.get_current_task() == "Step 2"
    print("✓ SessionState checklist navigation works")

    session.set_variable("key1", "value1")
    assert session.get_variable("key1") == "value1"
    print("✓ SessionState variable storage works")

    # Test serialization
    data = session.to_dict()
    restored = SessionState.from_dict(data)
    assert restored.goal == session.goal
    assert restored.current_step == session.current_step
    print("✓ SessionState serialization works")

    # Test ContextLedger
    ledger = ContextLedger(job_id="test-123")
    ledger.add_step(ReasoningStep(
        step_number=1,
        timestamp="2024-01-01T00:00:00Z",
        thought="Test thought",
        action={"tool": "test", "params": {}},
        observation="Test observation",
    ))
    assert len(ledger.reasoning_trace) == 1
    print("✓ ContextLedger trace recording works")

    trace_prompt = ledger.get_trace_for_prompt()
    assert "Step 1" in trace_prompt
    print("✓ ContextLedger prompt generation works")

    print("\n✓ Context Manager tests passed!")
    return True


def test_database_operations():
    """Test database operations for agent jobs."""
    print("\n" + "="*50)
    print("Testing Database Operations")
    print("="*50)

    from src.agent.context_manager import ContextManager
    from src.db.central_db import query
    import uuid

    cm = ContextManager()

    # Create a test job
    test_tenant = f"test-tenant-{uuid.uuid4().hex[:8]}"
    test_goal = "Test agent job for validation"

    try:
        job_id = cm.create_job(
            tenant_id=test_tenant,
            job_type="communication",
            goal=test_goal,
            checklist=["Step 1", "Step 2"],
            max_iterations=5,
        )
        print(f"✓ Created test job: {job_id}")

        # Verify job exists in DB (job_id is returned as string, need to cast for UUID column)
        rows = query("SELECT * FROM agent_jobs WHERE id = %s::uuid", [job_id])
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
        assert rows[0]["goal"] == test_goal
        print(f"✓ Verified job exists in database")

        # Load the session
        session = cm.load_session(job_id)
        assert session is not None, "Session should not be None"
        assert session.goal == test_goal, f"Goal mismatch: {session.goal} != {test_goal}"
        print(f"✓ Loaded session for job {job_id}")

        # Load the context
        ledger = cm.load_context(job_id)
        assert ledger is not None, "Ledger should not be None"
        print(f"✓ Loaded context for job {job_id}")

        # Update session
        session.add_thought("Test thought")
        session.advance_step()
        cm.save_session(session)
        print("✓ Saved session state")

        # Mark complete
        cm.mark_complete(job_id, "Test completed successfully")
        print("✓ Marked job complete")

        # Cleanup - delete test job
        query("DELETE FROM agent_jobs WHERE id = %s::uuid", [job_id])
        print("✓ Cleaned up test job")

        print("\n✓ Database operations tests passed!")
        return True

    except Exception as e:
        import traceback
        print(f"✗ Database test failed: {e}")
        traceback.print_exc()
        return False


def test_tool_execution():
    """Test that tools can execute (with mocked dependencies)."""
    print("\n" + "="*50)
    print("Testing Tool Execution")
    print("="*50)

    from src.agent.tools.registry import ToolRegistry
    from src.agent.tools.perception import register_perception_tools
    from src.agent.tools.processing import register_processing_tools
    from src.agent.tools.communication import register_communication_tools
    from src.agent.tools.persistence import register_persistence_tools

    registry = ToolRegistry()
    register_perception_tools(registry)
    register_processing_tools(registry)
    register_communication_tools(registry)
    register_persistence_tools(registry)

    # Test a simple processing tool that doesn't need external deps
    tool = registry.get("calculate_days_past_due")
    if tool:
        result = tool(due_date="2024-01-01")
        assert result.success
        assert result.data["is_past_due"] == True
        print(f"✓ calculate_days_past_due: {result.data['days_past_due']} days")

    # Test tool validation
    valid, err = registry.validate_action({
        "tool": "send_email",
        "params": {"tenant_id": "t1", "to": "test@example.com", "subject": "Hi", "body": "Hello"}
    })
    assert valid, f"Validation failed: {err}"
    print("✓ Tool validation works for valid input")

    valid, err = registry.validate_action({
        "tool": "send_email",
        "params": {"tenant_id": "t1"}  # Missing required params
    })
    assert not valid
    print("✓ Tool validation catches missing params")

    valid, err = registry.validate_action({
        "tool": "nonexistent_tool",
        "params": {}
    })
    assert not valid
    print("✓ Tool validation catches unknown tools")

    print("\n✓ Tool execution tests passed!")
    return True


def test_orchestrator_init():
    """Test that the orchestrator initializes correctly."""
    print("\n" + "="*50)
    print("Testing Orchestrator Initialization")
    print("="*50)

    from src.agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator(
        cycle_duration_seconds=60,
        poll_interval_ms=1000,
        max_concurrent_jobs=3,
    )

    # Check initialization
    assert orchestrator.cycle_duration == 60
    assert orchestrator.poll_interval == 1.0
    assert orchestrator.max_concurrent == 3
    print("✓ Orchestrator configuration works")

    # Check tool registry
    tools = orchestrator.tool_registry.list_tools()
    assert len(tools) >= 15  # We have ~20 tools
    print(f"✓ Tool registry initialized with {len(tools)} tools")

    # Check personas
    assert "communication" in orchestrator.personas
    assert "scheduler" in orchestrator.personas
    print("✓ Personas initialized")

    # Check status
    status = orchestrator.get_status()
    assert status["running"] == False
    assert status["active_jobs"] == 0
    print(f"✓ Status reporting works: {status}")

    print("\n✓ Orchestrator initialization tests passed!")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*50)
    print("Level 2 Agent Test Suite")
    print("="*50)

    tests = [
        ("Tool Registry", test_tool_registry),
        ("Personas", test_personas),
        ("Context Manager", test_context_manager),
        ("Database Operations", test_database_operations),
        ("Tool Execution", test_tool_execution),
        ("Orchestrator Init", test_orchestrator_init),
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
    print("Test Summary")
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
