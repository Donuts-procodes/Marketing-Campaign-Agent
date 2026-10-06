"""
Progress reporting contract shared by the research agent and its tool subagents.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

# Async callback receiving (message, level) progress lines; level is INFO, WARN or ERROR.
ProgressFn = Callable[[str, str], Awaitable[None]]


async def _report(on_progress: ProgressFn | None, message: str, level: str = "INFO") -> None:
    if on_progress is not None:
        await on_progress(message, level)
