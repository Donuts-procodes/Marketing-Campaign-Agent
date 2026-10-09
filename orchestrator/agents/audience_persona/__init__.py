"""
Audience Persona & ICP Profiling Agent Package.

Modular Architecture:
  - agent.py: Top-level agent orchestrator coordinating persona extraction and ICP profiling.
  - service.py: HTTP microservice wrapper for autonomous container deployment.
"""

from orchestrator.agents.audience_persona.agent import execute_audience_persona

__all__ = [
    "execute_audience_persona",
]
