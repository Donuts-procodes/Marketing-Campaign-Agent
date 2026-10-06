"""
Aggregate API v1 router.
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status

from orchestrator.api.endpoints import campaigns
from orchestrator.core.config import get_settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Rejects /api calls without the configured API_ACCESS_KEY (open when none is configured)."""
    expected = get_settings().api_access_key
    if expected and not (x_api_key and hmac.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")


api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])
api_router.include_router(campaigns.router)
