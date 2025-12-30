"""
ReAct Engine

The core reasoning loop that implements the ReAct (Reason + Act) pattern.
This is the "brain" of the Level 2 Agent.

Layer 1 of the 4-Layer Stack: Reasoning Core
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any
from openai import OpenAI

from src.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from src.logger import info, error, debug, warn

from .persona.base import AgentPersona, TaskDecomposition
from .tools.registry import ToolRegistry
from .tools.base import ToolResult
from .context_manager import SessionState, ContextLedger, ReasoningStep
from .metrics import AgentMetrics


@dataclass
class AgentResponse:
    """Parsed response from the LLM."""
    thought: str
    action: Optional[dict] = None
    checklist_update: Optional[list[str]] = None
    goal_achieved: bool = False
    needs_human: bool = False
    human_prompt: Optional[str] = None
    raw_response: str = ""
    parse_error: Optional[str] = None


class ReActEngine:
    """
    The ReAct reasoning engine.

    Implements the Thought -> Action -> Observation loop
    that drives autonomous agent behavior.
    """

    def __init__(
        self,
        persona: AgentPersona,
        tool_registry: ToolRegistry,
        max_iterations: int = 20,
        temperature: float = 0.3,
        metrics: AgentMetrics = None,
    ):
        self.persona = persona
        self.tools = tool_registry
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.metrics = metrics

        # Initialize LLM client
        if not DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY environment variable is required")

        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
        )

    def run(
        self,
        goal: str,
        session: SessionState,
        ledger: ContextLedger,
        tenant_id: str,
        initial_checklist: list[str] = None,
    ) -> tuple[bool, str, int]:
        """
        Run the ReAct loop until goal is achieved or max iterations reached.

        Args:
            goal: The high-level goal to achieve
            session: Session state for short-term memory
            ledger: Context ledger for long-term memory
            tenant_id: The tenant context
            initial_checklist: Optional pre-defined checklist

        Returns:
            Tuple of (success: bool, summary: str, iterations: int)
        """
        # Initialize or resume checklist
        if initial_checklist and not session.checklist:
            session.checklist = initial_checklist
        elif not session.checklist:
            # Decompose goal into steps
            session.checklist = self._decompose_goal(goal)

        info(f"Starting ReAct loop",
             goal=goal[:100],
             checklist_items=len(session.checklist),
             starting_iteration=session.iteration_count)

        while session.iteration_count < self.max_iterations:
            session.iteration_count += 1

            # Track reasoning iterations
            if self.metrics:
                self.metrics.reasoning_iterations_total.inc()

            # Build the prompt with current context
            system_prompt = self._build_system_prompt(session, ledger)
            user_prompt = self._build_user_prompt(goal, session, tenant_id)

            # Get LLM response
            response = self._call_llm(system_prompt, user_prompt)

            if response.parse_error:
                warn(f"Failed to parse LLM response",
                     error=response.parse_error,
                     iteration=session.iteration_count)
                # Try to recover
                session.add_thought(f"Parse error: {response.parse_error}")
                continue

            # Record the thought
            session.add_thought(response.thought)

            # Create reasoning step
            step = ReasoningStep(
                step_number=len(ledger.reasoning_trace) + 1,
                timestamp=datetime.utcnow().isoformat() + "Z",
                thought=response.thought,
                action=response.action,
            )

            # Check for goal completion
            if response.goal_achieved:
                step.observation = "Goal achieved"
                ledger.add_step(step)
                ledger.context_summary = self._generate_summary(session, ledger, "completed")
                info(f"Goal achieved after {session.iteration_count} iterations")
                return True, ledger.context_summary, session.iteration_count

            # Check for human handoff
            if response.needs_human:
                step.observation = f"Needs human: {response.human_prompt}"
                ledger.add_step(step)
                ledger.context_summary = self._generate_summary(session, ledger, "waiting_human")
                info(f"Requesting human assistance", prompt=response.human_prompt)
                return False, response.human_prompt, session.iteration_count

            # Update checklist if provided
            if response.checklist_update:
                session.checklist = response.checklist_update
                debug(f"Checklist updated", new_items=len(session.checklist))

            # Execute the action
            if response.action:
                result = self._execute_action(response.action, tenant_id)
                observation = result.to_observation()
                step.observation = observation

                # Handle self-correction
                if not result.success and result.needs_retry:
                    step.next_thought = f"Action failed: {result.error}. Will retry or adjust."
                elif result.success:
                    # Advance checklist if action succeeded
                    if session.current_step < len(session.checklist):
                        session.advance_step()

                ledger.add_step(step)

                debug(f"Action executed",
                      tool=response.action.get("tool"),
                      success=result.success,
                      iteration=session.iteration_count)
            else:
                step.observation = "No action specified"
                ledger.add_step(step)

            # Check if checklist is complete
            if session.is_complete():
                ledger.context_summary = self._generate_summary(session, ledger, "completed")
                info(f"Checklist complete after {session.iteration_count} iterations")
                return True, ledger.context_summary, session.iteration_count

        # Max iterations reached
        ledger.context_summary = self._generate_summary(session, ledger, "max_iterations")
        warn(f"Max iterations reached", iterations=self.max_iterations)
        return False, f"Max iterations ({self.max_iterations}) reached. {ledger.context_summary}", session.iteration_count

    def _decompose_goal(self, goal: str) -> list[str]:
        """Use LLM to break down a goal into actionable steps."""
        prompt = TaskDecomposition.get_decomposition_prompt(goal)

        try:
            response = self.client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": "You are a task planning assistant. Break down goals into clear, actionable steps."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500,
            )

            content = response.choices[0].message.content.strip()

            # Parse JSON array from response
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                steps = json.loads(match.group())
                return steps

            # Fallback: simple default steps
            return [
                "Analyze the current situation",
                "Execute the main task",
                "Verify completion",
            ]

        except Exception as e:
            error(f"Goal decomposition failed", err=e)
            return [goal]  # Use goal as single step

    def _build_system_prompt(self, session: SessionState, ledger: ContextLedger) -> str:
        """Build the system prompt with persona and tools."""
        # Get tools description
        tools_desc = self.tools.get_prompt_descriptions()

        # Build complete prompt
        prompt = self.persona.get_system_prompt()
        prompt += f"\n\n{self.persona.format_tools_prompt(tools_desc)}"

        if ledger.context_summary:
            prompt += f"\n\n{self.persona.get_context_hydration_prompt(ledger.context_summary)}"

        if session.checklist:
            prompt += f"\n\n{self.persona.get_checklist_prompt(session.checklist, session.current_step)}"

        return prompt

    def _build_user_prompt(self, goal: str, session: SessionState, tenant_id: str) -> str:
        """Build the user prompt with current context."""
        parts = [f"GOAL: {goal}", f"TENANT: {tenant_id}"]

        # Add recent thoughts for context
        recent = session.get_recent_thoughts(5)
        if recent:
            thoughts_str = "\n".join(f"- {t['thought']}" for t in recent)
            parts.append(f"RECENT THOUGHTS:\n{thoughts_str}")

        # Add current task
        current = session.get_current_task()
        if current:
            parts.append(f"CURRENT TASK: {current}")

        # Add session variables if any
        if session.variables:
            vars_str = json.dumps(session.variables, indent=2, default=str)
            parts.append(f"SESSION VARIABLES:\n{vars_str}")

        parts.append("\nWhat is your next thought and action?")

        return "\n\n".join(parts)

    def _call_llm(self, system_prompt: str, user_prompt: str) -> AgentResponse:
        """Call the LLM and parse the response."""
        import time as time_module
        start_time = time_module.time()
        success = False
        tokens = 0

        try:
            response = self.client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=1500,
            )

            content = response.choices[0].message.content.strip()
            success = True

            # Track token usage if available
            if hasattr(response, 'usage') and response.usage:
                tokens = response.usage.total_tokens

            return self._parse_response(content)

        except Exception as e:
            error(f"LLM call failed", err=e)
            return AgentResponse(
                thought=f"Error calling LLM: {str(e)}",
                parse_error=str(e),
            )
        finally:
            if self.metrics:
                duration = time_module.time() - start_time
                self.metrics.llm_latency.observe(duration)
                self.metrics.record_llm_call(success, tokens)

    def _parse_response(self, content: str) -> AgentResponse:
        """Parse the LLM response into structured format."""
        # Try to extract JSON from response
        try:
            # Look for JSON block in markdown
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find raw JSON object
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                else:
                    # No JSON found, treat whole response as thought
                    return AgentResponse(
                        thought=content,
                        raw_response=content,
                        parse_error="No JSON found in response",
                    )

            data = json.loads(json_str)

            return AgentResponse(
                thought=data.get("thought", ""),
                action=data.get("action"),
                checklist_update=data.get("checklist_update"),
                goal_achieved=data.get("goal_achieved", False),
                needs_human=data.get("needs_human", False),
                human_prompt=data.get("human_prompt"),
                raw_response=content,
            )

        except json.JSONDecodeError as e:
            return AgentResponse(
                thought=content[:500],
                raw_response=content,
                parse_error=f"JSON parse error: {str(e)}",
            )

    def _execute_action(self, action: dict, tenant_id: str) -> ToolResult:
        """Execute a tool action."""
        import time as time_module
        tool_name = action.get("tool")
        params = action.get("params", {})

        # Inject tenant_id if the tool needs it and it's not provided
        if "tenant_id" not in params:
            params["tenant_id"] = tenant_id

        # Validate and execute
        valid, err = self.tools.validate_action(action)
        if not valid:
            if self.metrics:
                self.metrics.record_tool_call(tool_name, success=False)
            return ToolResult(
                success=False,
                error=err,
                suggested_action="Check tool parameters",
            )

        start_time = time_module.time()
        result = self.tools.execute(tool_name, **params)
        duration = time_module.time() - start_time

        if self.metrics:
            self.metrics.record_tool_call(tool_name, result.success, duration)

        return result

    def _generate_summary(
        self,
        session: SessionState,
        ledger: ContextLedger,
        status: str,
    ) -> str:
        """Generate a context summary for persistence."""
        completed_steps = session.checklist[:session.current_step]
        remaining_steps = session.checklist[session.current_step:]

        summary_parts = [
            f"Status: {status}",
            f"Iterations: {session.iteration_count}",
            f"Completed steps: {len(completed_steps)}",
        ]

        if completed_steps:
            summary_parts.append(f"Done: {', '.join(completed_steps[:3])}")

        if remaining_steps and status != "completed":
            summary_parts.append(f"Remaining: {', '.join(remaining_steps[:3])}")

        # Add last thought for context
        recent = session.get_recent_thoughts(1)
        if recent:
            summary_parts.append(f"Last thought: {recent[0]['thought'][:100]}")

        return " | ".join(summary_parts)


def create_react_engine(
    persona: AgentPersona,
    tool_registry: ToolRegistry = None,
    max_iterations: int = 20,
    metrics: AgentMetrics = None,
) -> ReActEngine:
    """
    Factory function to create a ReActEngine with default configuration.
    """
    if tool_registry is None:
        from .tools.registry import get_registry
        from .tools.perception import register_perception_tools
        from .tools.communication import register_communication_tools
        from .tools.processing import register_processing_tools
        from .tools.persistence import register_persistence_tools

        tool_registry = get_registry()
        register_perception_tools(tool_registry)
        register_communication_tools(tool_registry)
        register_processing_tools(tool_registry)
        register_persistence_tools(tool_registry)

    return ReActEngine(
        persona=persona,
        tool_registry=tool_registry,
        max_iterations=max_iterations,
        metrics=metrics,
    )
