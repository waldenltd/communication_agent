"""
Tool Base Class

Defines the standard interface for all agent tools.
Each tool is a callable with a JSON schema that the LLM can invoke.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
import json


class ToolCategory(Enum):
    """Categories of tools available to the agent."""
    PERCEPTION = "perception"      # Observe current state
    PROCESSING = "processing"      # Transform/analyze data
    PERSISTENCE = "persistence"    # Database operations
    COMMUNICATION = "communication"  # External messaging


@dataclass
class ToolParameter:
    """Definition of a tool parameter for JSON schema generation."""
    name: str
    type: str  # "string", "integer", "boolean", "object", "array"
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[list] = None
    items: Optional[dict] = None  # For array types
    properties: Optional[dict] = None  # For object types

    def to_json_schema(self) -> dict:
        """Convert to JSON schema format."""
        schema = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        if self.items:
            schema["items"] = self.items
        if self.properties:
            schema["properties"] = self.properties
        return schema


@dataclass
class ToolResult:
    """Result of executing a tool."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    side_effects: list = field(default_factory=list)

    # For self-correction hints
    needs_retry: bool = False
    retry_reason: Optional[str] = None
    suggested_action: Optional[str] = None

    def to_observation(self) -> str:
        """Convert result to observation string for ReAct loop."""
        if self.success:
            if isinstance(self.data, dict):
                return json.dumps(self.data, indent=2, default=str)
            return str(self.data) if self.data else "Action completed successfully."
        else:
            obs = f"Error: {self.error}"
            if self.suggested_action:
                obs += f"\nSuggested action: {self.suggested_action}"
            return obs


class Tool(ABC):
    """
    Base class for all agent tools.

    Tools are the "hands" of the agent - they perform actual actions
    in response to the agent's decisions.
    """

    def __init__(
        self,
        name: str,
        description: str,
        category: ToolCategory,
        parameters: list[ToolParameter] = None,
    ):
        self.name = name
        self.description = description
        self.category = category
        self.parameters = parameters or []

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with the given parameters.

        Must be implemented by each concrete tool.
        """
        pass

    def validate_params(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate parameters before execution."""
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                return False, f"Missing required parameter: {param.name}"

            if param.name in kwargs and param.enum:
                if kwargs[param.name] not in param.enum:
                    return False, f"Invalid value for {param.name}. Must be one of: {param.enum}"

        return True, None

    def __call__(self, **kwargs) -> ToolResult:
        """Make tools callable directly."""
        valid, error = self.validate_params(**kwargs)
        if not valid:
            return ToolResult(success=False, error=error)
        return self.execute(**kwargs)

    def to_json_schema(self) -> dict:
        """
        Generate JSON schema for LLM tool calling.

        Format compatible with Claude/OpenAI function calling.
        """
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        }

    def to_prompt_description(self) -> str:
        """Generate a description suitable for system prompts."""
        params_desc = []
        for p in self.parameters:
            req = "(required)" if p.required else "(optional)"
            params_desc.append(f"  - {p.name} [{p.type}] {req}: {p.description}")

        params_str = "\n".join(params_desc) if params_desc else "  (no parameters)"

        return f"""**{self.name}** [{self.category.value}]
{self.description}
Parameters:
{params_str}"""


class FunctionTool(Tool):
    """
    Tool that wraps an existing function.

    Useful for wrapping existing handlers/providers as tools
    without rewriting them.
    """

    def __init__(
        self,
        name: str,
        description: str,
        category: ToolCategory,
        func: Callable,
        parameters: list[ToolParameter] = None,
        result_transformer: Callable[[Any], ToolResult] = None,
    ):
        super().__init__(name, description, category, parameters)
        self._func = func
        self._result_transformer = result_transformer or self._default_transformer

    def _default_transformer(self, result: Any) -> ToolResult:
        """Default transformation of function result to ToolResult."""
        if isinstance(result, ToolResult):
            return result
        if isinstance(result, Exception):
            return ToolResult(success=False, error=str(result))
        return ToolResult(success=True, data=result)

    def execute(self, **kwargs) -> ToolResult:
        """Execute the wrapped function."""
        try:
            result = self._func(**kwargs)
            return self._result_transformer(result)
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                needs_retry=True,
                retry_reason=f"Exception during execution: {type(e).__name__}",
            )
