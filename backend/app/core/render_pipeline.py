"""
render_pipeline.py
-------------------
Core graphics/rendering pipeline for the ZentraX backend: turns a scene
description into a rendered frame suitable for hologram, AR, or VR delivery.

Design goals:
  - A staged pipeline (asset prep -> geometry -> shading -> compositing ->
    output) so individual stages can be swapped, profiled, or parallelized
    independently.
  - Fully async so it composes cleanly with FastAPI/websocket handlers and
    the async AssetLoader.
  - Defensive error handling: a failure in one frame should not crash the
    pipeline or the server process, only that frame.
  - Basic performance metrics (per-stage and per-frame timing) since
    real-time delivery is latency-sensitive.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from asset_loader import AssetError, AssetLoader

logger = logging.getLogger("zentrax.render_pipeline")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class RenderPipelineError(Exception):
    """Base class for pipeline-level failures."""


class StageExecutionError(RenderPipelineError):
    """Raised when a single pipeline stage fails."""

    def __init__(self, stage_name: str, original: Exception):
        self.stage_name = stage_name
        self.original = original
        super().__init__(f"Stage '{stage_name}' failed: {original}")


# --------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------

class RenderTarget(str, Enum):
    HOLOGRAM = "hologram"
    AR = "ar"
    VR = "vr"
    MEDIA = "media"


@dataclass
class SceneObject:
    object_id: str
    asset_path: str
    transform: Dict[str, Any] = field(default_factory=dict)  # position/rotation/scale
    material: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CameraState:
    position: Sequence[float] = (0.0, 0.0, 0.0)
    orientation: Sequence[float] = (0.0, 0.0, 0.0, 1.0)  # quaternion
    fov_degrees: float = 60.0


@dataclass
class FrameContext:
    """Mutable state threaded through each pipeline stage for one frame."""
    session_id: str
    target: RenderTarget
    scene_objects: List[SceneObject]
    camera: CameraState
    frame_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = field(default_factory=time.time)
    resolved_assets: Dict[str, Any] = field(default_factory=dict)
    geometry: Dict[str, Any] = field(default_factory=dict)
    shaded: Dict[str, Any] = field(default_factory=dict)
    output: Optional[Any] = None
    stage_timings_ms: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class FrameResult:
    frame_id: str
    session_id: str
    target: RenderTarget
    output: Any
    total_time_ms: float
    stage_timings_ms: Dict[str, float]
    warnings: List[str]


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------

class PipelineStage(ABC):
    """A single, named step in the render pipeline."""

    name: str = "unnamed_stage"

    @abstractmethod
    async def process(self, ctx: FrameContext) -> FrameContext:
        ...


class AssetPreparationStage(PipelineStage):
    """Resolves and caches all assets referenced by the scene."""

    name = "asset_preparation"

    def __init__(self, asset_loader: AssetLoader):
        self._asset_loader = asset_loader

    async def process(self, ctx: FrameContext) -> FrameContext:
        async def _resolve(obj: SceneObject):
            try:
                asset = await self._asset_loader.load(obj.asset_path)
                ctx.resolved_assets[obj.object_id] = asset
            except AssetError as exc:
                ctx.warnings.append(
                    f"Skipping object '{obj.object_id}': asset error: {exc}"
                )

        await asyncio.gather(*(_resolve(o) for o in ctx.scene_objects))
        return ctx


class GeometryStage(PipelineStage):
    """Builds/transforms geometry buffers for objects that resolved cleanly."""

    name = "geometry"

    async def process(self, ctx: FrameContext) -> FrameContext:
        for obj in ctx.scene_objects:
            if obj.object_id not in ctx.resolved_assets:
                continue  # already flagged as a warning in asset prep
            ctx.geometry[obj.object_id] = {
                "transform": obj.transform,
                "asset_metadata": ctx.resolved_assets[obj.object_id].metadata,
            }
        return ctx


class ShadingStage(PipelineStage):
    """Applies materials/lighting to prepared geometry."""

    name = "shading"

    async def process(self, ctx: FrameContext) -> FrameContext:
        for obj in ctx.scene_objects:
            geo = ctx.geometry.get(obj.object_id)
            if geo is None:
                continue
            ctx.shaded[obj.object_id] = {
                **geo,
                "material": obj.material,
            }
        return ctx


class CompositingStage(PipelineStage):
    """Composites shaded objects relative to the camera into a single frame."""

    name = "compositing"

    async def process(self, ctx: FrameContext) -> FrameContext:
        ctx.output = {
            "frame_id": ctx.frame_id,
            "camera": {
                "position": ctx.camera.position,
                "orientation": ctx.camera.orientation,
                "fov_degrees": ctx.camera.fov_degrees,
            },
            "objects": list(ctx.shaded.values()),
            "object_count": len(ctx.shaded),
        }
        return ctx


class OutputStage(PipelineStage):
    """
    Final target-specific packaging step. Hologram/AR/VR/media targets may
    need different packaging (e.g. stereo pairs for VR); this stage is the
    seam where that specialization happens.
    """

    name = "output"

    async def process(self, ctx: FrameContext) -> FrameContext:
        if ctx.output is None:
            raise RenderPipelineError("OutputStage reached with no composited output")
        ctx.output["target"] = ctx.target.value
        return ctx


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

class RenderPipeline:
    """
    Orchestrates an ordered sequence of PipelineStages, providing timing,
    per-stage error isolation, and a simple hook for custom stage sets
    (e.g. a leaner pipeline for low-power AR devices).
    """

    def __init__(self, stages: Optional[List[PipelineStage]] = None,
                 asset_loader: Optional[AssetLoader] = None):
        self._asset_loader = asset_loader or AssetLoader()
        self._stages: List[PipelineStage] = stages or self._default_stages()

    def _default_stages(self) -> List[PipelineStage]:
        return [
            AssetPreparationStage(self._asset_loader),
            GeometryStage(),
            ShadingStage(),
            CompositingStage(),
            OutputStage(),
        ]

    def add_stage(self, stage: PipelineStage, index: Optional[int] = None) -> None:
        if index is None:
            self._stages.append(stage)
        else:
            self._stages.insert(index, stage)

    def remove_stage(self, stage_name: str) -> None:
        self._stages = [s for s in self._stages if s.name != stage_name]

    async def render_frame(
        self,
        session_id: str,
        target: RenderTarget,
        scene_objects: List[SceneObject],
        camera: CameraState,
    ) -> FrameResult:
        ctx = FrameContext(
            session_id=session_id,
            target=target,
            scene_objects=scene_objects,
            camera=camera,
        )

        frame_start = time.perf_counter()
        for stage in self._stages:
            stage_start = time.perf_counter()
            try:
                ctx = await stage.process(ctx)
            except Exception as exc:
                logger.exception("Pipeline stage '%s' raised an error", stage.name)
                raise StageExecutionError(stage.name, exc) from exc
            finally:
                ctx.stage_timings_ms[stage.name] = (time.perf_counter() - stage_start) * 1000

        total_time_ms = (time.perf_counter() - frame_start) * 1000

        if ctx.warnings:
            logger.warning(
                "Frame %s for session %s completed with %d warning(s): %s",
                ctx.frame_id, session_id, len(ctx.warnings), "; ".join(ctx.warnings),
            )

        return FrameResult(
            frame_id=ctx.frame_id,
            session_id=session_id,
            target=target,
            output=ctx.output,
            total_time_ms=total_time_ms,
            stage_timings_ms=ctx.stage_timings_ms,
            warnings=ctx.warnings,
        )

    async def render_stream(
        self,
        session_id: str,
        target: RenderTarget,
        frame_source,
        max_concurrent_frames: int = 1,
    ):
        """
        Async generator: consumes an async iterator of (scene_objects, camera)
        tuples and yields FrameResults. max_concurrent_frames > 1 allows
        pipelined rendering at the cost of possible frame reordering, so it
        is opt-in and left at 1 (strict order) by default.
        """
        semaphore = asyncio.Semaphore(max_concurrent_frames)

        async def _render_one(scene_objects, camera):
            async with semaphore:
                try:
                    return await self.render_frame(session_id, target, scene_objects, camera)
                except RenderPipelineError as exc:
                    logger.error("Dropping frame for session %s: %s", session_id, exc)
                    return None

        async for scene_objects, camera in frame_source:
            result = await _render_one(scene_objects, camera)
            if result is not None:
                yield result

