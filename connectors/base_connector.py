"""
Abstract base class for all SaaS connectors.

Every connector must implement the abstract methods below.
The base class provides:
  - Structured logging with connector context
  - Token bucket rate limiting
  - Retry with exponential backoff (via tenacity)
  - Progress tracking
  - Standard error taxonomy
"""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)


# ── Custom exceptions ─────────────────────────────────────────────────────────

class ConnectorError(Exception):
    """Base class for all connector errors."""


class AuthError(ConnectorError):
    """Invalid or expired credentials."""


class RateLimitError(ConnectorError):
    """API rate limit exceeded."""


class NetworkError(ConnectorError):
    """Transient network failure."""


class ParseError(ConnectorError):
    """Unexpected response format."""


# ── Progress tracker ──────────────────────────────────────────────────────────

@dataclass
class SyncProgress:
    connector_name: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    records_fetched: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.completed_at is None:
            return "running"
        return "failed" if self.errors else "completed"

    def record_error(self, stage: str, error: str) -> None:
        self.errors.append({"stage": stage, "error": error, "ts": datetime.now(timezone.utc).isoformat()})
        log.error("sync_error", extra={"connector": self.connector_name, "stage": stage, "error": error})

    def finish(self) -> None:
        self.completed_at = datetime.now(timezone.utc)


# ── Base connector ────────────────────────────────────────────────────────────

class BaseConnector(ABC):
    """
    Abstract base class for SSPM connectors.

    Subclasses must implement:
      authenticate, test_connection, fetch_users, fetch_groups,
      fetch_permissions, fetch_resources, normalize_data, sync
    """

    #: Short lowercase name, e.g. "github", "okta"
    platform_name: str = "unknown"

    def __init__(self, credentials: dict[str, str], config: dict[str, Any] | None = None):
        self._credentials = credentials
        self._config = config or {}
        self._log = logging.getLogger(f"sspm.connectors.{self.platform_name}")
        self._progress: SyncProgress | None = None

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Validate credentials.

        Returns:
            True if authentication succeeded.
        Raises:
            AuthError on invalid credentials.
        """

    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        """
        Test connectivity and return metadata about the connected account.

        Returns:
            dict with at least {"ok": bool, "platform": str, "identity": str}
        """

    @abstractmethod
    def fetch_users(self) -> list[dict[str, Any]]:
        """Return a list of normalized user dicts."""

    @abstractmethod
    def fetch_groups(self) -> list[dict[str, Any]]:
        """Return a list of normalized group dicts."""

    @abstractmethod
    def fetch_permissions(self) -> list[dict[str, Any]]:
        """Return a list of normalized permission dicts."""

    @abstractmethod
    def fetch_resources(self) -> list[dict[str, Any]]:
        """Return a list of normalized resource dicts."""

    @abstractmethod
    def normalize_data(self, raw_data: dict[str, Any], entity_type: str) -> dict[str, Any]:
        """
        Convert a platform-specific API response into the canonical SSPM schema.

        Args:
            raw_data:    Raw JSON dict from the platform API.
            entity_type: One of "user", "group", "resource", "permission".

        Returns:
            Normalized dict matching the corresponding Pydantic schema.
        """

    @abstractmethod
    def sync(self) -> SyncProgress:
        """
        Run a full sync: authenticate → fetch all entity types → persist.

        Returns:
            SyncProgress with final stats and any errors.
        """

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _start_progress(self) -> SyncProgress:
        self._progress = SyncProgress(connector_name=self.platform_name)
        self._log.info("sync_started", extra={"connector": self.platform_name})
        return self._progress

    def _finish_progress(self) -> SyncProgress:
        assert self._progress is not None
        self._progress.finish()
        self._log.info(
            "sync_finished",
            extra={
                "connector": self.platform_name,
                "status": self._progress.status,
                "records": self._progress.records_fetched,
                "errors": len(self._progress.errors),
            },
        )
        return self._progress
