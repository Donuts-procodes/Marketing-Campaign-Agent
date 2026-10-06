"""Container log hygiene: one format, no polling spam, no reload ceremony."""

from __future__ import annotations

import logging

import pytest

from orchestrator.core.log_format import (
    AccessLogFilter,
    ColorFormatter,
    LifecycleNoiseFilter,
    configure_logging,
)

#: uvicorn.access passes (client_addr, method, full_path, http_version, status_code).
_ACCESS_FMT = '%s - "%s %s HTTP/%s" %d'


def _access_record(path: str, status: int, method: str = "GET") -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, _ACCESS_FMT,
        ("172.18.0.5:51610", method, path, "1.1", status), None,
    )


def _message_record(message: str, name: str = "uvicorn.error") -> logging.LogRecord:
    return logging.LogRecord(name, logging.INFO, "", 0, message, (), None)


class TestAccessLogFilter:
    @pytest.mark.parametrize(
        "path",
        ["/api/v1/campaigns/sessions?limit=50", "/healthz", "/favicon.ico", "/openapi.json"],
    )
    def test_drops_successful_polls(self, path):
        assert AccessLogFilter().filter(_access_record(path, 200)) is False

    @pytest.mark.parametrize("status", [400, 404, 500, 503])
    def test_keeps_failures_on_polled_endpoints(self, status):
        """A failing poll is the thing you actually need to see."""
        assert AccessLogFilter().filter(_access_record("/healthz", status)) is True

    @pytest.mark.parametrize(
        "path",
        ["/api/v1/campaigns", "/api/v1/campaigns/job-1/events", "/api/v1/campaigns/job-1/report"],
    )
    def test_keeps_real_endpoints(self, path):
        assert AccessLogFilter().filter(_access_record(path, 200)) is True

    def test_keeps_record_when_args_are_unexpected(self):
        """Unparseable record: keep it rather than hide something real."""
        record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "odd line", (), None)
        assert AccessLogFilter().filter(record) is True


class TestLifecycleNoiseFilter:
    @pytest.mark.parametrize(
        "message",
        [
            "Waiting for application startup.",
            "Waiting for application shutdown.",
            "Application shutdown complete.",
            "Finished server process [14]",
            "Started server process [19]",
            "Shutting down",
        ],
    )
    def test_drops_reload_ceremony(self, message):
        assert LifecycleNoiseFilter().filter(_message_record(message)) is False

    @pytest.mark.parametrize(
        "message",
        [
            "Application startup complete.",
            "WatchFiles detected changes in 'synthesis.py'. Reloading...",
            "Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)",
        ],
    )
    def test_keeps_informative_lines(self, message):
        """What changed, and that it came back up -- the two lines worth printing."""
        assert LifecycleNoiseFilter().filter(_message_record(message)) is True


class TestUnifiedFormatting:
    def test_uvicorn_loggers_share_the_app_handler(self):
        configure_logging()
        app_handlers = logging.getLogger("orchestrator").handlers
        assert app_handlers, "app logger should have a handler"
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            uvicorn_logger = logging.getLogger(name)
            assert uvicorn_logger.handlers, f"{name} should be routed to our handler"
            assert all(
                isinstance(h.formatter, ColorFormatter) for h in uvicorn_logger.handlers
            ), f"{name} still formats differently from the app"
            assert uvicorn_logger.propagate is False

    def test_is_idempotent(self):
        configure_logging()
        before = len(logging.getLogger("orchestrator").handlers)
        configure_logging()
        configure_logging()
        assert len(logging.getLogger("orchestrator").handlers) == before

    def test_plain_format_has_no_ansi_codes(self):
        formatter = ColorFormatter(use_color=False)
        rendered = formatter.format(_message_record("hello [TAVILY_SEARCH] world", "orchestrator"))
        assert "\033[" not in rendered
        assert "hello [TAVILY_SEARCH] world" in rendered

    def test_noisy_libraries_are_quieted(self):
        configure_logging()
        for name in ("httpx", "watchfiles", "pymongo"):
            assert logging.getLogger(name).level >= logging.WARNING
