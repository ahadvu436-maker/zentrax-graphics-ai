"""
backend/app/api/endpoints.py

Zentrax AI Graphics — API endpoints for generating design assets
(logos, banners, etc.) from a text prompt.

This module currently simulates the actual AI generation step so the
frontend/API contract can be built and tested before the real image
generation pipeline is wired in.
"""

import asyncio
import random
import uuid
from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api/v1/design", tags=["Design Generation"])


# --------------------------------------------------------------------------- #
# Enums & Schemas
# --------------------------------------------------------------------------- #

class DesignType(str, Enum):
    LOGO = "logo"
    BANNER = "banner"


class DesignRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Text prompt describing the desired design.",
        examples=["A minimalist logo for a coffee brand called 'Brewhaus'"],
    )
    design_type: DesignType = Field(
        ...,
        description="Type of design to generate: 'logo' or 'banner'.",
    )

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Prompt cannot be empty or whitespace only.")
        return value.strip()


class DesignResponse(BaseModel):
    request_id: str
    status: str
    design_type: DesignType
    prompt: str
    image_url: str
    thumbnail_url: str
    created_at: datetime


# --------------------------------------------------------------------------- #
# Internal helpers (mock generation logic)
# --------------------------------------------------------------------------- #

# Dimensions differ by design type — used only to make the mock URL
# realistic; swap this out for real generation params later.
_DESIGN_DIMENSIONS = {
    DesignType.LOGO: "512x512",
    DesignType.BANNER: "1500x500",
}


async def _simulate_ai_generation(prompt: str, design_type: DesignType) -> dict:
    """
    Placeholder for the real AI image-generation call.

    Simulates network/model latency and returns a mock image URL.
    Replace the body of this function with a call to the actual
    generation service (e.g. Stable Diffusion, an internal model
    endpoint, or a third-party API) when it's ready.
    """
    # Simulate variable processing time (e.g. queueing + inference)
    await asyncio.sleep(random.uniform(0.5, 1.5))

    image_id = uuid.uuid4().hex
    dimensions = _DESIGN_DIMENSIONS[design_type]

    return {
        "image_url": f"https://cdn.zentrax.ai/generated/{design_type.value}/{image_id}_{dimensions}.png",
        "thumbnail_url": f"https://cdn.zentrax.ai/generated/{design_type.value}/{image_id}_thumb.png",
    }


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

@router.post(
    "/generate",
    response_model=DesignResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a design asset from a text prompt",
)
async def generate_design(request: DesignRequest) -> DesignResponse:
    """
    Accepts a text prompt and a design type (logo/banner), simulates
    an AI generation pipeline, and returns a mock image URL along
    with metadata about the request.
    """
    try:
        result = await _simulate_ai_generation(request.prompt, request.design_type)
    except Exception as exc:
        # In a real pipeline this could catch model timeouts,
        # rate-limit errors, etc. and translate them appropriately.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Design generation failed: {exc}",
        ) from exc

    return DesignResponse(
        request_id=str(uuid.uuid4()),
        status="completed",
        design_type=request.design_type,
        prompt=request.prompt,
        image_url=result["image_url"],
        thumbnail_url=result["thumbnail_url"],
        created_at=datetime.now(timezone.utc),
    )