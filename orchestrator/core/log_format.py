"""
Colorized console logging: level badges plus a distinct color per pipeline tag
("[TAVILY_SEARCH]", "[DEEP_SEARCH]", ...) so each tool subagent is easy to follow.

Colors are disabled when the stream is not a TTY or NO_COLOR is set; FORCE_COLOR forces them
on (useful under Docker, where stdout is not a TTY).
"""

from __future__ import annotations

import logging
import os
import re
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

LEVEL_STYLES = {
    "DEBUG": "\033[37;100m",      # grey badge
    "INFO": "\033[30;46m",        # black on cyan
    "WARNING": "\033[30;43m",     # black on yellow
    "ERROR": "\033[97;41m",       # white on red
    "CRITICAL": "\033[97;45m",    # white on magenta
}

# One color per pipeline stage / tool subagent; keep in sync with client LiveConsole TAG_STYLES.
TAG_STYLES = {
    "DYNAMIC_PARAMS": "\033[95m",     # magenta
    "TAVILY_SEARCH": "\033[94m",      # blue
    "DEEP_SEARCH": "\033[96m",        # cyan
    "DQS_EVAL": "\033[92m",           # green
    "AD_INTELLIGENCE": "\033[93m",    # yellow
    "LLM_SYNTH": "\033[35m",          # purple
    "DATA_VALIDATION": "\033[32m",    # dark green
    "CONFIG": "\033[33m",             # orange-ish
    "LLM_CONFIG": "\033[91m",         # red
}
DEFAULT_TAG_STYLE = "\033[36m"

_TAG_RE = re.compile(r"\[([A-Z][A-Z0-9_]+)\]")


def _colors_enabled(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


class ColorFormatter(logging.Formatter):
    def __init__(self, use_color: bool | None = None) -> None:
        """`use_color=None` auto-detects, so a dictConfig factory taking no arguments still
        respects NO_COLOR / FORCE_COLOR / whether the stream is a terminal."""
        super().__init__(datefmt="%H:%M:%S")
        self.use_color = _colors_enabled(sys.stderr) if use_color is None else use_color

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        timestamp = self.formatTime(record, self.datefmt)
        level = record.levelname

        if not self.use_color:
            return f"{timestamp} {level:<8} {record.name}: {message}"

        badge = f"{LEVEL_STYLES.get(level, '')}{BOLD} {level:<7} {RESET}"
        message = _TAG_RE.sub(
            lambda m: f"{TAG_STYLES.get(m.group(1), DEFAULT_TAG_STYLE)}{BOLD}[{m.group(1)}]{RESET}",
            message,
        )
        return f"{DIM}{timestamp}{RESET} {badge} {DIM}{record.name}{RESET} {message}"


#: Endpoints the UI polls on a timer. Logging every successful poll buries real output, so
#: only their failures are kept.
QUIET_ACCESS_PATHS = (
    "/api/v1/campaigns/sessions",
    "/healthz",
    "/health",
    "/favicon.ico",
    "/docs",
    "/openapi.json",
)

#: Uvicorn's per-restart ceremony. Under --reload this is ~7 lines every time a file is
#: saved, which drowns out the two lines that actually matter: what changed, and that the
#: app came back up.
_LIFECYCLE_NOISE = (
    "Waiting for application startup",
    "Waiting for application shutdown",
    "Application shutdown complete",
    "Finished server process",
    "Started server process",
    "Started reloader process",
    "Shutting down",
)


class AccessLogFilter(logging.Filter):
    """Drops successful requests to polled endpoints; keeps every error and everything else."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args if isinstance(record.args, tuple) else ()
        # uvicorn.access passes (client_addr, method, full_path, http_version, status_code)
        path = args[2] if len(args) > 2 and isinstance(args[2], str) else record.getMessage()
        if not any(p in str(path) for p in QUIET_ACCESS_PATHS):
            return True
        status = args[4] if len(args) > 4 else None
        try:
            return int(status) >= 400  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return True  # cannot tell -- keep it rather than hide something real


class LifecycleNoiseFilter(logging.Filter):
    """Collapses uvicorn's reload ceremony to the lines that carry information."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(noise in message for noise in _LIFECYCLE_NOISE)


def configure_logging(level: int = logging.INFO) -> None:
    """
    Routes the app's loggers and uvicorn's through one formatter (idempotent).

    Uvicorn installs its own handlers with a different format, so without this the container
    log interleaves two styles. Its loggers are re-pointed at our handler and stopped from
    propagating, and the high-frequency noise is filtered out.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(ColorFormatter(use_color=_colors_enabled(sys.stderr)))
    handler.addFilter(LifecycleNoiseFilter())
    handler._orchestrator_color = True  # type: ignore[attr-defined]

    # Exactly one of our handlers per logger, and nothing else. Converging on that state
    # rather than bailing out early keeps this idempotent AND removes any handler uvicorn
    # installed on its own -- two handlers on one logger prints every line twice.
    for name in ("orchestrator", "uvicorn", "uvicorn.error", "uvicorn.access"):
        target = logging.getLogger(name)
        ours = [h for h in target.handlers if isinstance(h.formatter, ColorFormatter)]
        target.handlers = ours[:1] or [handler]
        target.propagate = False
        target.setLevel(level)

    logging.getLogger("uvicorn.access").addFilter(AccessLogFilter())

    # Third-party libraries chatter at INFO about connection pools and retries.
    for noisy in ("httpx", "httpcore", "urllib3", "watchfiles", "pymongo", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
