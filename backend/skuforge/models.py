"""Pydantic models for the pipeline."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SKUInput(BaseModel):
    mpn: str
    brand: str
    description: str = ""


class SourceType(str, Enum):
    manufacturer = "manufacturer"
    distributor = "distributor"
    marketplace = "marketplace"
    other = "other"


class Source(BaseModel):
    url: str
    title: str = ""
    source_type: SourceType = SourceType.other
    is_pdf: bool = False
    fetched_at: Optional[str] = None


class Evidence(BaseModel):
    """One extracted attribute value from one source."""
    source_url: str
    source_type: SourceType
    raw_value: str
    quote: str = ""  # supporting text snippet from the source


class AttributeStatus(str, Enum):
    verified = "verified"          # >=2 agreeing sources
    single_source = "single-source"
    conflict = "conflict"
    generated = "generated"        # LLM-inferred, no source


class Attribute(BaseModel):
    name: str
    value: str
    unit: str = ""
    confidence: float = 0.0
    status: AttributeStatus = AttributeStatus.generated
    evidence: list[Evidence] = []
    conflicting_values: list[Evidence] = []
    human_reviewed: bool = False


class RecordStatus(str, Enum):
    processing = "processing"
    auto_approved = "auto-approved"
    needs_review = "needs-review"
    approved = "approved"
    failed = "failed"


class ProductRecord(BaseModel):
    id: str
    input: SKUInput
    category: str = ""
    category_confidence: float = 0.0
    seo_title: str = ""
    short_description: str = ""
    long_description: str = ""
    attributes: list[Attribute] = []
    search_synonyms: list[str] = []
    certifications: list[str] = []
    image_urls: list[str] = []
    datasheet_urls: list[str] = []
    equivalent_mpns: list[str] = []
    sources: list[Source] = []
    status: RecordStatus = RecordStatus.processing
    cost_usd: float = 0.0
    duration_s: float = 0.0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PipelineEvent(BaseModel):
    """Streamed to the frontend agent-theatre panel via SSE."""
    record_id: str
    agent: str          # scout | classifier | extractor | validator | composer
    step: str           # human-readable action, e.g. "Found datasheet PDF"
    detail: dict[str, Any] = {}
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
