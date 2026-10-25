"""Pydantic models for screenshot facts: every extraction backend's output and the cache
file are validated against these before the pipeline reads them."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

RESOURCE_PATTERN = (r"^(account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|"
                    r"legal_hold|marketing|email_delivery|cache|object)_\d+$")
RecordType = Literal["USER_PROFILE", "SEARCH_INDEX_ENTRY", "ANALYTICS_PROFILE", "SUPPORT_MESSAGE",
                     "SUPPORT_ATTACHMENT", "USER_EXPORT", "MARKETING_PROFILE", "DATA_FLOW", "BACKUP_ARCHIVE",
                     "SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD", "ACCOUNT_TOMBSTONE"]
Result = Literal["FOUND", "NOT_FOUND", "IDENTIFIABLE", "ANONYMIZED", "REDACTED", "ACTIVE", "DISABLED",
                 "BLOCKED"]


class ExtractedRecord(BaseModel):
    """One resource read off a screenshot, with exactly what was visible for it."""
    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(pattern=RESOURCE_PATTERN)
    record_type: Optional[RecordType] = None
    result: Optional[Result] = None
    email: Optional[str] = Field(default=None, pattern=r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
    customer_reference: Optional[str] = Field(default=None, pattern=r"^user_\d+$")
    phone: Optional[str] = None
    full_name: Optional[str] = None
    enabled: Optional[bool] = None
    restore_allowed: Optional[bool] = None
    related_resource_ids: list[str] = Field(default_factory=list)
    note: Optional[str] = None

    @field_validator("related_resource_ids")
    @classmethod
    def _related_are_resources(cls, value: list[str]) -> list[str]:
        import re
        bad = [v for v in value if not re.match(RESOURCE_PATTERN, v)]
        if bad:
            raise ValueError(f"not resource ids: {bad}")
        return sorted(set(value))


class ImageFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    screen: str
    extracted_by: str                     # backend and model/engine name
    records: list[ExtractedRecord]
    source_sha256: str                    # hash of the PNG the facts were read from
    rejected_tokens: list[str] = Field(default_factory=list)   # read but failed validation


class ImageFactsCache(RootModel[dict[str, ImageFacts]]):
    pass
