"""
Tool Registry

Central registry for all agent tools with discovery and dispatch.
"""

from typing import Optional
from src.logger import info, error, debug
from .base import Tool, ToolResult, ToolCategory


class ToolRegistry:
    """
    Central registry for agent tools.

    Provides:
    - Tool registration and discovery
    - JSON schema generation for LLM
    - Tool dispatch with logging
    - Category-based filtering
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._by_category: dict[ToolCategory, list[str]] = {
            cat: [] for cat in ToolCategory
        }

    def register(self, tool: Tool) -> None:
        """Register a tool in the registry."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")

        self._tools[tool.name] = tool
        self._by_category[tool.category].append(tool.name)

        debug(f"Registered tool: {tool.name}",
              category=tool.category.value,
              params=[p.name for p in tool.parameters])

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        if name in self._tools:
            tool = self._tools[name]
            self._by_category[tool.category].remove(name)
            del self._tools[name]

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self, category: Optional[ToolCategory] = None) -> list[str]:
        """List all tool names, optionally filtered by category."""
        if category:
            return self._by_category[category].copy()
        return list(self._tools.keys())

    def execute(self, name: str, **kwargs) -> ToolResult:
        """
        Execute a tool by name with the given parameters.

        Includes logging and error handling.
        """
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {name}",
                suggested_action="Check available tools with list_tools()"
            )

        info(f"Executing tool: {name}",
             category=tool.category.value,
             params=list(kwargs.keys()))

        try:
            result = tool(**kwargs)

            if result.success:
                debug(f"Tool {name} succeeded",
                      side_effects=result.side_effects)
            else:
                error(f"Tool {name} failed",
                      error=result.error,
                      needs_retry=result.needs_retry)

            return result

        except Exception as e:
            error(f"Tool {name} raised exception", err=e)
            return ToolResult(
                success=False,
                error=str(e),
                needs_retry=True,
                retry_reason=f"Unhandled exception: {type(e).__name__}"
            )

    def get_all_schemas(self) -> list[dict]:
        """Get JSON schemas for all registered tools."""
        return [tool.to_json_schema() for tool in self._tools.values()]

    def get_schemas_by_category(self, category: ToolCategory) -> list[dict]:
        """Get JSON schemas for tools in a specific category."""
        return [
            self._tools[name].to_json_schema()
            for name in self._by_category[category]
        ]

    def get_prompt_descriptions(self, category: Optional[ToolCategory] = None) -> str:
        """
        Generate tool descriptions suitable for system prompts.

        Groups tools by category for better LLM comprehension.
        """
        sections = []

        categories = [category] if category else list(ToolCategory)

        for cat in categories:
            tool_names = self._by_category[cat]
            if not tool_names:
                continue

            section = f"## {cat.value.upper()} TOOLS\n\n"
            for name in tool_names:
                tool = self._tools[name]
                section += tool.to_prompt_description() + "\n\n"

            sections.append(section)

        return "\n".join(sections)

    def validate_action(self, action: dict) -> tuple[bool, Optional[str]]:
        """
        Validate an action dict from LLM output.

        Expected format:
        {
            "tool": "tool_name",
            "params": {"param1": "value1", ...}
        }
        """
        if not isinstance(action, dict):
            return False, "Action must be a dictionary"

        if "tool" not in action:
            return False, "Action must have 'tool' key"

        tool_name = action["tool"]
        if tool_name not in self._tools:
            available = ", ".join(self._tools.keys())
            return False, f"Unknown tool '{tool_name}'. Available: {available}"

        params = action.get("params", {})
        if not isinstance(params, dict):
            return False, "Action 'params' must be a dictionary"

        tool = self._tools[tool_name]
        return tool.validate_params(**params)


# Global registry instance
_global_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get or create the global tool registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def register_tool(tool: Tool) -> None:
    """Register a tool in the global registry."""
    get_registry().register(tool)
