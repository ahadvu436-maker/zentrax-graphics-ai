"""
backend/app/services/ai_engine.py

AI generation service for Zentrax — wraps an external image-generation
API (e.g. Stability AI / Stable Diffusion) behind a clean interface.
Swap `_call_external_api` for a local SD pipeline (diffusers) if you
move generation in-house later; the rest of the app doesn't need to know.
"""

import asyncio
import base64
import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.models.schemas import DesignStyle, Resolution

logger = logging.getLogger("zentrax.ai_engine")

# Stability AI's SD image endpoint accepts specific dimension pairs.
# Map our public Resolution enum -> valid (width, height) for the model.
_RESOLUTION_MAP: dict[Resolution, tuple[int, int]] = {
    Resolution.SQ_512: (512, 512),
    Resolution.SQ_1024: (1024, 1024),
    Resolution.BANNER_WIDE: (1536, 640),   # nearest supported to 1500x500
    Resolution.BANNER_STANDARD: (1216, 640),
    Resolution.HD: (1344, 768),
}

_STYLE_PROMPT_HINTS: dict[DesignStyle, str] = {
    DesignStyle.MINIMALIST: "minimalist, clean lines, flat design, plenty of negative space",
    DesignStyle.REALISTIC: "photorealistic, highly detailed, natural lighting",
    DesignStyle.CARTOON: "cartoon style, bold outlines, vibrant colors",
    DesignStyle.VINTAGE: "vintage aesthetic, retro color palette, aged texture",
    DesignStyle.ABSTRACT: "abstract art, geometric shapes, artistic composition",
    DesignStyle.CORPORATE: "professional, corporate, polished, brand-safe",
    DesignStyle.THREE_D: "3d render, octane render, studio lighting, high detail",
}


@dataclass
class GeneratedImage:
    """In-memory result of a single generation, before upload."""
    content: bytes
    content_type: str = "image/png"
    seed: Optional[int] = None


class AIGenerationError(Exception):
    """Raised when the upstream generation service fails or times out."""


class AIEngine:
    """
    Thin async client around the external image generation API.

    Usage:
        engine = AIEngine()
        image = await engine.generate_image(prompt=..., style=..., resolution=...)
    """

    def __init__(self) -> None:
        if not settings.AI_GENERATION_API_KEY or not settings.AI_GENERATION_BASE_URL:
            logger.warning(
                "AI_GENERATION_API_KEY / AI_GENERATION_BASE_URL not configured — "
                "AIEngine will fail on real requests until these are set."
            )
        self._base_url = settings.AI_GENERATION_BASE_URL
        self._api_key = settings.AI_GENERATION_API_KEY
        self._timeout = httpx.Timeout(60.0, connect=10.0)
        self._max_retries = 2

    # --------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------- #

    async def generate_image(
        self,
        prompt: str,
        style: DesignStyle,
        resolution: Resolution,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        num_variations: int = 1,
    ) -> list[GeneratedImage]:
        """Generate one or more images for a generic image/banner request."""
        full_prompt = self._build_prompt(prompt, style)
        width, height = _RESOLUTION_MAP.get(resolution, (1024, 1024))

        return await self._call_external_api(
            prompt=full_prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            seed=seed,
            samples=num_variations,
        )

    async def generate_logo(
        self,
        prompt: str,
        brand_name: str,
        style: DesignStyle,
        resolution: Resolution,
        tagline: Optional[str] = None,
        transparent_background: bool = True,
        seed: Optional[int] = None,
    ) -> GeneratedImage:
        """Generate a single logo, composed with brand-specific prompt hints."""
        logo_prompt = (
            f"{prompt}, logo design for brand '{brand_name}'"
            f"{f', with tagline \"{tagline}\"' if tagline else ''}"
            f"{', on a transparent background, isolated on white' if transparent_background else ''}"
        )
        full_prompt = self._build_prompt(logo_prompt, style)
        width, height = _RESOLUTION_MAP.get(resolution, (1024, 1024))

        images = await self._call_external_api(
            prompt=full_prompt,
            negative_prompt="text artifacts, watermark, blurry, low quality",
            width=width,
            height=height,
            seed=seed,
            samples=1,
        )
        return images[0]

    # --------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------- #

    def _build_prompt(self, base_prompt: str, style: DesignStyle) -> str:
        hint = _STYLE_PROMPT_HINTS.get(style, "")
        return f"{base_prompt}, {hint}" if hint else base_prompt

    async def _call_external_api(
        self,
        prompt: str,
        width: int,
        height: int,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        samples: int = 1,
    ) -> list[GeneratedImage]:
        """
        Calls the external generation API with retry/backoff.
        Expects a JSON response containing one or more base64-encoded
        images (matches Stability AI's response shape) — adjust the
        parsing block if you switch providers.
        """
        if not self._base_url or not self._api_key:
            raise AIGenerationError("AI generation service is not configured.")

        payload = {
            "text_prompts": [
                {"text": prompt, "weight": 1.0},
                *([{"text": negative_prompt, "weight": -1.0}] if negative_prompt else []),
            ],
            "width": width,
            "height": height,
            "samples": samples,
            "cfg_scale": 7,
            "steps": 30,
            **({"seed": seed} if seed is not None else {}),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        last_error: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 2):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        f"{self._base_url}/v1/generation/image",
                        json=payload,
                        headers=headers,
                    )
                response.raise_for_status()
                data = response.json()
                return self._parse_response(data)

            except httpx.HTTPStatusError as exc:
                last_error = exc
                # Don't retry on 4xx (bad request / auth) — only on 5xx / timeouts
                if exc.response.status_code < 500:
                    break
                logger.warning("AI API 5xx on attempt %d: %s", attempt, exc)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning("AI API network error on attempt %d: %s", attempt, exc)

            if attempt <= self._max_retries:
                await asyncio.sleep(2 ** attempt)  # exponential backoff

        logger.error("AI generation failed after retries: %s", last_error)
        raise AIGenerationError(f"Image generation failed: {last_error}") from last_error

    @staticmethod
    def _parse_response(data: dict) -> list[GeneratedImage]:
        artifacts = data.get("artifacts")
        if not artifacts:
            raise AIGenerationError("AI service returned no image artifacts.")

        images: list[GeneratedImage] = []
        for artifact in artifacts:
            b64 = artifact.get("base64")
            if not b64:
                continue
            images.append(
                GeneratedImage(
                    content=base64.b64decode(b64),
                    content_type="image/png",
                    seed=artifact.get("seed"),
                )
            )

        if not images:
            raise AIGenerationError("AI service response contained no decodable images.")
        return images


def get_ai_engine() -> AIEngine:
    """FastAPI dependency factory: Depends(get_ai_engine)"""
    return AIEngine()