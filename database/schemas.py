"""
Pydantic schemas for API request/response validation and normalized entity payloads.
"""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ── Normalized entity payloads (stored in normalized_entities.data_json) ─────

class NormalizedUser(BaseModel):
    entity_type: Literal["user"] = "user"
    platform: str
    platform_id: str
    email: str | None = None
    username: str
    display_name: str | None = None
    is_active: bool = True
    is_external: bool = False
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedGroup(BaseModel):
    entity_type: Literal["group"] = "group"
    platform: str
    platform_id: str
    name: str
    description: str | None = None
    member_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedResource(BaseModel):
    entity_type: Literal["resource"] = "resource"
    platform: str
    platform_id: str
    name: str
    resource_subtype: str  # e.g. "repository", "bucket", "workspace"
    is_public: bool = False
    owner_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedPermission(BaseModel):
    entity_type: Literal["permission"] = "permission"
    platform: str
    grantee_id: str          # user or group platform_id
    grantee_type: str        # "user" | "group"
    resource_id: str
    role: str                # e.g. "admin", "write", "read"
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── API – Connector ────────────────────────────────────────────────────────────

class ConnectorCreate(BaseModel):
    platform_name: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=256)
    credentials: dict[str, str] = Field(..., description="Raw credentials; will be encrypted at rest")
    config: dict[str, Any] = Field(default_factory=dict)


class ConnectorResponse(BaseModel):
    id: UUID
    platform_name: str
    display_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    connection_ok: bool | None = None
    last_sync_at: datetime | None = None
    last_sync_error: str | None = None
    sync_interval_minutes: int | None = None

    model_config = {"from_attributes": True}


class ConnectorScheduleRequest(BaseModel):
    sync_interval_minutes: int | None = Field(
        None,
        description="Auto-sync interval in minutes. NULL disables auto-sync.",
        ge=5,
    )


class ConnectorCredentialsUpdate(BaseModel):
    credentials: dict[str, str] = Field(
        ...,
        description="New credentials (e.g. rotated API token). Encrypted at rest.",
    )


class ConnectorStatusResponse(BaseModel):
    connector_id: UUID
    platform_name: str
    display_name: str
    connection_ok: bool | None
    last_sync_at: datetime | None
    last_sync_error: str | None

    model_config = {"from_attributes": True}


# ── API – ScanRun ─────────────────────────────────────────────────────────────

class ScanRunResponse(BaseModel):
    id: UUID
    connector_id: UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    records_fetched: int
    findings_count: int = 0
    connection_ok: bool | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ── API – Finding ─────────────────────────────────────────────────────────────

class StatusUpdateRequest(BaseModel):
    status: str = Field(..., description="resolved | false_positive | accepted_risk | open")
    justification: str | None = Field(
        None,
        description="Required when status is false_positive or accepted_risk",
    )


class FindingResponse(BaseModel):
    id: int
    rule_id: str
    severity: str
    status: str
    description: str
    platform: str
    connector_id: UUID | None = None
    connector_name: str | None = None
    resource_identifier: str
    justification: str | None = None
    status_changed_at: datetime | None = None
    first_detected: datetime | None = None
    last_detected: datetime | None = None
    llm_severity: str | None = None
    llm_severity_reasoning: str | None = None
    llm_exploitability: str | None = None
    llm_remediation: str | None = None
    llm_confidence: float | None = None
    llm_analyzed_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Generic ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict[str, str]


class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None
