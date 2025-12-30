"""
Agent Persona Base Class

Defines the structure for agent personas - the "Prime Directive" that
instructs the LLM how to behave, reason, and make decisions.

Layer 1 of the 4-Layer Stack: Persona & Reasoning Core
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentPersona(ABC):
    """
    Base class for agent personas.

    A persona defines:
    - Who the agent is (identity and role)
    - How the agent thinks (reasoning patterns)
    - What the agent values (good taste rules)
    - How the agent communicates (output format)
    """

    name: str
    description: str
    good_taste_rules: list[str] = field(default_factory=list)

    # ReAct pattern enforcement
    REACT_INSTRUCTIONS = """
## REASONING PATTERN (ReAct)

You MUST follow the ReAct (Reason + Act) pattern for every decision:

1. **THOUGHT**: State your current understanding and what you need to accomplish.
   - What is the current state?
   - What is the goal?
   - What should I do next?

2. **ACTION**: Choose ONE tool to execute from the available tools.
   - Select the most appropriate tool
   - Provide all required parameters
   - Only execute ONE action at a time

3. **OBSERVATION**: After receiving the result, analyze it.
   - Did the action succeed?
   - What did I learn?
   - Does this change my plan?

4. **ITERATE**: Decide if the goal is achieved or if you need to continue.
   - If goal achieved: Report completion
   - If not achieved: Return to THOUGHT with new information
   - If blocked: Request human assistance

IMPORTANT RULES:
- Never skip the THOUGHT step
- Never execute multiple actions at once
- Always observe and reflect on results
- Self-correct when things go wrong
- Ask for human help when stuck after 3 attempts
"""

    OUTPUT_FORMAT_INSTRUCTIONS = """
## OUTPUT FORMAT

You must respond with valid JSON in the following format:

```json
{
  "thought": "Your current reasoning about the situation...",
  "action": {
    "tool": "tool_name",
    "params": {
      "param1": "value1",
      "param2": "value2"
    }
  },
  "checklist_update": ["optional", "updated", "checklist"],
  "goal_achieved": false,
  "needs_human": false,
  "human_prompt": null
}
```

Field descriptions:
- `thought`: Your reasoning (required)
- `action`: The tool to execute (null if goal achieved or needs human)
- `checklist_update`: Updated task list if replanning is needed (optional)
- `goal_achieved`: True when the overall goal is complete
- `needs_human`: True when you need human input to proceed
- `human_prompt`: Question for human if needs_human is true
"""

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Generate the complete system prompt for this persona.

        Must include:
        - Identity and role
        - Good taste rules
        - ReAct instructions
        - Output format
        - Available tools (injected by caller)
        """
        pass

    def get_identity_prompt(self) -> str:
        """Get the identity/role portion of the prompt."""
        return f"""# IDENTITY

You are {self.name}.

{self.description}
"""

    def get_good_taste_prompt(self) -> str:
        """Get the good taste rules portion of the prompt."""
        if not self.good_taste_rules:
            return ""

        rules = "\n".join(f"- {rule}" for rule in self.good_taste_rules)
        return f"""## GOOD TASTE (Decision Guidelines)

When making decisions, follow these principles:

{rules}
"""

    def get_context_hydration_prompt(self, context_summary: Optional[str]) -> str:
        """Get the context hydration portion if resuming a session."""
        if not context_summary:
            return ""

        return f"""## PREVIOUS SESSION CONTEXT

You are resuming a previous task. Here is what happened before:

{context_summary}

Continue from where you left off.
"""

    def get_checklist_prompt(self, checklist: list[str], current_step: int) -> str:
        """Get the current task checklist prompt."""
        if not checklist:
            return ""

        items = []
        for i, item in enumerate(checklist):
            marker = ">>>" if i == current_step else "   "
            status = "[DONE]" if i < current_step else "[TODO]" if i == current_step else "[    ]"
            items.append(f"{marker} {status} {i+1}. {item}")

        return f"""## CURRENT CHECKLIST

{chr(10).join(items)}

Focus on the current step marked with ">>>".
"""

    def format_tools_prompt(self, tools_description: str) -> str:
        """Format the available tools section."""
        return f"""## AVAILABLE TOOLS

{tools_description}

Use these tools to accomplish your tasks. Always check preconditions before acting.
"""


@dataclass
class TaskDecomposition:
    """
    Helper for breaking down high-level goals into actionable steps.
    """

    DECOMPOSITION_PROMPT = """
Given a high-level goal, break it down into concrete, actionable steps.

Guidelines:
- Each step should be a single, atomic action
- Steps should be in logical order
- Include verification steps where appropriate
- Keep the list focused (5-10 steps typically)

Format your response as a JSON array of strings:
["Step 1: ...", "Step 2: ...", ...]
"""

    @staticmethod
    def get_decomposition_prompt(goal: str) -> str:
        """Get a prompt for decomposing a goal into steps."""
        return f"""{TaskDecomposition.DECOMPOSITION_PROMPT}

GOAL: {goal}

Break this goal into actionable steps:"""
