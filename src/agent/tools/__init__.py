"""
Agent Tools Module

Provides the Tool interface and registry for agent actions.
All tools follow a standard JSON schema interface for LLM consumption.

Categories:
- Perception: check_*, get_* (observe current state)
- Processing: generate_*, calculate_* (transform data)
- Persistence: save_*, load_*, query_* (database operations)
- Communication: send_*, notify_* (external messaging)
"""

from .base import Tool, ToolResult, ToolParameter, ToolCategory
from .registry import ToolRegistry

__all__ = [
    'Tool',
    'ToolResult',
    'ToolParameter',
    'ToolCategory',
    'ToolRegistry',
]
