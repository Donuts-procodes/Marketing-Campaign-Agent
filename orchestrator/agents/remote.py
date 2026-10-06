"""
Remote Agent Microservice Client Adapter.

Provides a LangGraph-compatible node callable that dispatches agent execution
to an independent HTTP microservice over network, with automatic local fallback
when running offline, in test suites, or during transient network disconnects.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

import httpx

from orchestrator.core.config import get_settings
from orchestrator.schemas.research import SWOTReportDelta
from orchestrator.schemas.state import StrategyState

logger = logging.getLogger(__name__)


def _serialize_state_for_http(state: StrategyState) -> dict[str, Any]:
    """Ensures nested Pydantic models in StrategyState are dumped to JSON-compatible dicts."""
    serialized: dict[str, Any] = {}
    for k, v in state.items():
        if hasattr(v, "model_dump"):
            serialized[k] = v.model_dump()
        elif isinstance(v, dict):
            serialized[k] = {
                sub_k: sub_v.model_dump() if hasattr(sub_v, "model_dump") else sub_v
                for sub_k, sub_v in v.items()
            }
        else:
            serialized[k] = v
    return serialized


def _deserialize_response_delta(delta: dict[str, Any]) -> dict[str, Any]:
    """Reconstructs typed Pydantic models from microservice response payload."""
    reconstructed = dict(delta)
    if "swot_report" in reconstructed and isinstance(reconstructed["swot_report"], dict):
        reconstructed["swot_report"] = SWOTReportDelta.model_validate(reconstructed["swot_report"])
    return reconstructed


class RemoteAgentNode:
    """
    HTTP Client Node that forwards graph state to a remote agent microservice.
    """

    def __init__(
        self,
        agent_name: str,
        service_url: str = "",
        *,
        fallback_fn: Callable[[StrategyState], Awaitable[dict[str, Any]]] | None = None,
        timeout: float = 120.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.service_url = service_url.rstrip("/")
        self.fallback_fn = fallback_fn
        self.timeout = timeout
        self._external_client = http_client

    async def __call__(self, state: StrategyState) -> dict[str, Any]:
        """
        Executes the agent via remote HTTP microservice or in-process fallback.
        """
        if not self.service_url:
            if self.fallback_fn is not None:
                return await self.fallback_fn(state)
            raise ValueError(
                f"Agent '{self.agent_name}' has no configured service URL and no local fallback."
            )

        payload = _serialize_state_for_http(state)
        endpoint = f"{self.service_url}/execute"

        try:
            client = self._external_client or httpx.AsyncClient(timeout=self.timeout)
            try:
                token = get_settings().agent_service_token
                headers = {"X-Agent-Token": token} if token else None
                response = await client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
                raw_delta = response.json()
                return _deserialize_response_delta(raw_delta)
            finally:
                if self._external_client is None:
                    await client.aclose()

        except Exception as exc:
            if self.fallback_fn is not None:
                logger.warning(
                    "Remote agent '%s' at %s failed (%s); engaging in-process fallback.",
                    self.agent_name,
                    endpoint,
                    exc,
                )
                return await self.fallback_fn(state)

            logger.error("Remote agent '%s' call failed with no fallback: %s", self.agent_name, exc)
            raise RuntimeError(
                f"Remote agent microservice '{self.agent_name}' failed at {endpoint}: {exc}"
            ) from exc
