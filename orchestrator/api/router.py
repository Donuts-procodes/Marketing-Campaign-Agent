"""
Aggregate API v1 router.
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status

from orchestrator.api.endpoints import campaigns
from orchestrator.core.config import get_settings


# Takes: x_api_key (str | None from HTTP header 'X-API-Key')
# Returns: None (raises HTTPException 401 if key does not match)
# Called by: FastAPI dependency injection on every /api/v1 route
# Points to / Calls: get_settings().api_access_key, hmac.compare_digest
def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Rejects /api calls without the configured API_ACCESS_KEY (open when none is configured)."""
    expected = get_settings().api_access_key
    if expected and not (x_api_key and hmac.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")


api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])
api_router.include_router(campaigns.router)


@api_router.get("/health/providers", tags=["health"], summary="Scraping and data-provider account status")
async def provider_health() -> list[dict]:
    """Reads each provider's free account endpoint; no page is fetched and no credit is spent."""
    from orchestrator.agents.market_research.ingestion.provider_health import check_providers

    return await check_providers()
