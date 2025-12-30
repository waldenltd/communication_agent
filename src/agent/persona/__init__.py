"""
Agent Persona Module

Defines the "who" and "how" for the agent - the system prompts
and reasoning patterns that guide behavior.
"""

from .base import AgentPersona
from .communication import CommunicationAgentPersona

__all__ = [
    'AgentPersona',
    'CommunicationAgentPersona',
]
