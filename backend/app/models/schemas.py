"""
backend/app/models/schemas.py

Pydantic schemas for Zentrax AI Graphics — request/response contracts
for image and logo generation endpoints.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

class DesignType(str, Enum):
    LOGO = "logo"
    BANNER = "banner"
    IMAGE = "image"


class DesignStyle(str, Enum):
    MINIMALIST = "minimalist"
    REALISTIC = "realistic"
    CARTOON = "cartoon"
    VINTAGE = "vintage"
    ABSTRACT = "abstract"
    CORPORATE = "corporate"
    THREE_D = "3d_render"


class ColorMode(str, Enum):
    COLOR = "color"
    MONOCHROME = "monochrome"
    DUOTONE = "duotone"


class Resolution(str, Enum):
    SQ_512 = "512x512"
    SQ_1024 = "1024x1024"
    BANNER_WIDE = "1500x500"
    BANNER_STANDARD = "1200x628"
    HD = "1920x1080"


class GenerationStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# --------------------------------------------------------------------------- #
# Shared base
# --------------------------------------------------------------------------- #

class GenerationRequestBase(BaseModel):
    """Common fields shared by all generation request types."""

    prompt: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Text description of the desired design.",
        examples=["A minimalist coffee cup icon with steam rising"],
    )
    style: DesignStyle = Field(
        default=DesignStyle.MINIMALIST,
        description="Visual style to apply to the generation.",
    )
    color_mode: ColorMode = Field(default=ColorMode.COLOR)
    negative_prompt: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Elements to avoid in the generated design.",
    )
    seed: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional seed for reproducible generation.",
    )

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Prompt cannot be empty or whitespace only.")
        return v.strip()


# --------------------------------------------------------------------------- #
# Request schemas
# --------------------------------------------------------------------------- #

class LogoGenerationRequest(GenerationRequestBase):
    """Request payload for generating a logo."""

    brand_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Brand or company name to feature in the logo.",
    )
    tagline: Optional[str] = Field(default=None, max_length=150)
    resolution: Resolution = Field(default=Resolution.SQ_1024)
    transparent_background: bool = Field(
        default=True,
        description="Whether the logo should be generated with a transparent background.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "prompt": "A modern geometric fox mascot logo",
                "brand_name": "Brewhaus",
                "tagline": "Coffee, crafted daily",
                "style": "minimalist",
                "color_mode": "color",
                "resolution": "1024x1024",
                "transparent_background": True,
            }
        }
    }


class ImageGenerationRequest(GenerationRequestBase):
    """Request payload for generic image / banner generation."""

    design_type: DesignType = Field(
        default=DesignType.IMAGE,
        description="Type of image being generated (image or banner).",
    )
    resolution: Resolution = Field(default=Resolution.HD)
    num_variations: int = Field(
        default=1,
        ge=1,
        le=4,
        description="Number of design variations to generate (1-4).",
    )

    @field_validator("design_type")
    @classmethod
    def design_type_not_logo(cls, v: DesignType) -> DesignType:
        if v == DesignType.LOGO:
            raise ValueError(
                "Use the /logo generation endpoint for logo requests, not /image."
            )
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "prompt": "A wide banner of a sunset over a mountain range, warm tones",
                "design_type": "banner",
                "style": "realistic",
                "resolution": "1500x500",
                "num_variations": 2,
            }
        }
    }


# --------------------------------------------------------------------------- #
# Response schemas
# --------------------------------------------------------------------------- #

class GeneratedAsset(BaseModel):
    """A single generated file result."""

    asset_id: UUID = Field(default_factory=uuid4)
    file_url: HttpUrl
    thumbnail_url: Optional[HttpUrl] = None
    resolution: Resolution


class GenerationResponse(BaseModel):
    """Response returned after a generation request is submitted/completed."""

    request_id: UUID = Field(default_factory=uuid4)
    status: GenerationStatus
    design_type: DesignType
    prompt: str
    style: DesignStyle
    assets: List[GeneratedAsset] = Field(default_factory=list)
    error_message: Optional[str] = Field(
        default=None,
        description="Populated only when status is 'failed'.",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "status": "completed",
                "design_type": "logo",
                "prompt": "A modern geometric fox mascot logo",
                "style": "minimalist",
                "assets": [
                    {
                        "asset_id": "9c858901-8a57-4791-81fe-4c455b099bc9",
                        "file_url": "https://cdn.zentrax.ai/generated/logo/abc123.png",
                        "thumbnail_url": "https://cdn.zentrax.ai/generated/logo/abc123_thumb.png",
                        "resolution": "1024x1024",
                    }
                ],
                "error_message": None,
                "created_at": "2026-09-10T12:00:00Z",
                "completed_at": "2026-09-10T12:00:03Z",
            }
        }
    }


class GenerationStatusResponse(BaseModel):
    """Lightweight response for polling a generation request's status."""

    request_id: UUID
    status: GenerationStatus
    progress_percent: int = Field(default=0, ge=0, le=100)
    assets: List[GeneratedAsset] = Field(default_factory=list)
    error_message: Optional[str] = None