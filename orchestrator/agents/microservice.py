"""
Agent Microservice Application Factory.

Enables each agent to run as an independent, autonomous microservice exposing
standardized HTTP endpoints (/health, /info, /execute) for containerized dispatch.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from orchestrator.core.config import get_settings
from orchestrator.schemas.state import StrategyState

AGENT_TOKEN_HEADER = "X-Agent-Token"


def require_agent_token(x_agent_token: str | None = Header(default=None)) -> None:
    """Rejects /execute calls without the shared service token, when one is configured."""
    expected = get_settings().agent_service_token
    if not expected:
        return
    if not x_agent_token or not hmac.compare_digest(x_agent_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")

logger = logging.getLogger(__name__)


class AgentHealthResponse(BaseModel):
    status: str = Field(default="healthy")
    agent: str
    version: str


class AgentInfoResponse(BaseModel):
    agent: str
    description: str
    version: str
    service_endpoint: str = ""
    models: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    input_schema: str = "StrategyState"
    output_schema: str = "StrategyDelta"


def create_agent_microservice(
    agent_name: str,
    execute_fn: Callable[[StrategyState], Awaitable[dict[str, Any]]],
    *,
    description: str = "",
    version: str = "0.1.0",
    service_endpoint: str = "",
    models: list[str] | None = None,
    tools: list[str] | None = None,
    capabilities: list[str] | None = None,
    input_schema: str = "StrategyState",
    output_schema: str = "StrategyDelta",
) -> FastAPI:
    """
    Constructs a standalone FastAPI microservice application for a given agent.

    Args:
        agent_name: Machine-readable agent identifier (e.g. "market_research").
        execute_fn: Async callable that takes StrategyState and returns a partial state delta.
        description: Human-readable service description.
        version: Semantic version string.
        service_endpoint: Container/host network endpoint (e.g. "http://agent_market_research:8001").
        models: LLMs and reasoning models used by this agent.
        tools: Internal and external tools integrated.
        capabilities: List of capability identifiers supported by the agent.
        input_schema: Inbound state type contract.
        output_schema: Outbound delta type contract.

    Returns:
        Configured FastAPI instance ready for Uvicorn execution.
    """
    from orchestrator.core.log_format import configure_logging

    configure_logging()
    app = FastAPI(
        title=f"{agent_name.replace('_', ' ').title()} Agent Microservice",
        description=description or f"Autonomous microservice for {agent_name} agent.",
        version=version,
    )

    caps = capabilities or []
    agent_models = models or []
    agent_tools = tools or []

    @app.get("/health", response_model=AgentHealthResponse, tags=["Health"])
    async def health_check() -> AgentHealthResponse:
        return AgentHealthResponse(
            status="healthy",
            agent=agent_name,
            version=version,
        )

    @app.get("/info", response_model=AgentInfoResponse, tags=["Metadata"])
    async def service_info() -> AgentInfoResponse:
        return AgentInfoResponse(
            agent=agent_name,
            description=description,
            version=version,
            service_endpoint=service_endpoint,
            models=agent_models,
            tools=agent_tools,
            capabilities=caps,
            input_schema=input_schema,
            output_schema=output_schema,
        )

    @app.post("/execute", tags=["Execution"], dependencies=[Depends(require_agent_token)])
    async def execute_agent(payload: dict[str, Any]) -> dict[str, Any]:
        """
        Executes the agent workflow against the provided StrategyState.
        Returns a partial state update delta to be merged by the orchestrator.
        """
        try:
            # Type cast to StrategyState contract
            state_input: StrategyState = payload  # type: ignore[assignment]
            result_delta = await execute_fn(state_input)
            return result_delta
        except Exception as exc:
            logger.error("Microservice execution failure in %s: %s", agent_name, exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Agent {agent_name} execution failed ({type(exc).__name__}).",
            ) from exc

    return app
