"""
hologram_engine.py
-------------------
Manages holographic display stages and multi-viewer volumetric content for
the ZentraX backend: stage calibration, viewer/parallax tracking, placing
content in volumetric space, and driving the render pipeline to produce a
per-viewer hologram frame (since glasses-free/multi-angle hologram displays
typically need a distinct view per viewing angle, not one shared camera).

Design goals:
  - Separate a HologramStage (the physical/virtual display's calibration:
    dimensions, projector/emitter layout) from a HologramSession (a live
    instance of content + tracked viewers in front of that stage).
  - Support N simultaneous viewers per stage, each getting their own
    rendered view, mirroring how a light-field or multi-user hologram
    display works - analogous to per-player VR rendering, but keyed by
    viewing angle rather than a first-person camera.
  - Volumetric content placement (position within the stage's working
    volume) is validated against stage bounds up front, so bad placements
    fail fast instead of silently rendering off-stage.
  - Stays render-pipeline-agnostic: this module builds CameraState/
    SceneObjects per viewer and delegates actual rendering to
    RenderPipeline, exactly like ar_controller.py and
    vr_environment_manager.py do for their targets.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from app.graphics.render_pipeline import (
        CameraState,
        FrameResult,
        RenderPipeline,
        RenderPipelineError,
        RenderTarget,
        SceneObject,
    )
    from app.graphics.asset_loader import AssetLoader, AssetError
except ImportError:  # pragma: no cover - fallback for flat/local layouts
    from render_pipeline import (
        CameraState,
        FrameResult,
        RenderPipeline,
        RenderPipelineError,
        RenderTarget,
        SceneObject,
    )
    from asset_loader import AssetLoader, AssetError

logger = logging.getLogger("zentrax.hologram_engine")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class HologramEngineError(Exception):
    """Base class for hologram engine failures."""


class StageNotFoundError(HologramEngineError):
    """Raised when referencing an unregistered stage_id."""


class HologramSessionNotFoundError(HologramEngineError):
    """Raised when referencing an unknown hologram session_id."""


class ViewerNotFoundError(HologramEngineError):
    """Raised when referencing a viewer not present in a session."""


class ContentNotFoundError(HologramEngineError):
    """Raised when referencing unknown placed content."""


class OutOfVolumeError(HologramEngineError):
    """Raised when content placement falls outside the stage's working volume."""


class StageCalibrationError(HologramEngineError):
    """Raised when a stage's calibration data is missing or invalid."""


# --------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------

class StageType(str, Enum):
    VOLUMETRIC_DISPLAY = "volumetric_display"   # e.g. light-field / swept-volume unit
    PEPPERS_GHOST = "peppers_ghost"              # angled-glass reflection rig
    GLASSES_FREE_LIGHTFIELD = "glasses_free_lightfield"
    PROJECTION_FOG = "projection_fog"


@dataclass
class WorkingVolume:
    """Axis-aligned bounding box of the stage's physical/virtual display volume, in meters."""
    width: float
    height: float
    depth: float
    origin: Sequence[float] = (0.0, 0.0, 0.0)  # volume center, in stage-local space

    def contains(self, position: Sequence[float]) -> bool:
        x, y, z = position[0], position[1], position[2]
        ox, oy, oz = self.origin
        return (
            abs(x - ox) <= self.width / 2
            and abs(y - oy) <= self.height / 2
            and abs(z - oz) <= self.depth / 2
        )


@dataclass
class HologramStage:
    """Calibration and capability data for one physical or virtual hologram display."""
    stage_id: str
    name: str
    stage_type: StageType
    working_volume: WorkingVolume
    max_viewers: int = 4
    calibrated: bool = False
    calibration_data: Dict[str, object] = field(default_factory=dict)


@dataclass
class ViewerPose:
    """A tracked viewer's position relative to the stage, used for parallax/view selection."""
    position: Sequence[float] = (0.0, 0.0, 1.0)
    orientation: Sequence[float] = (0.0, 0.0, 0.0, 1.0)
    timestamp: float = field(default_factory=time.time)


@dataclass
class Viewer:
    viewer_id: str
    pose: ViewerPose = field(default_factory=ViewerPose)
    joined_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_updated = time.time()


@dataclass
class PlacedContent:
    """A piece of content positioned within a stage's working volume."""
    content_id: str
    asset_path: str
    position: Sequence[float] = (0.0, 0.0, 0.0)
    orientation: Sequence[float] = (0.0, 0.0, 0.0, 1.0)
    scale: Sequence[float] = (1.0, 1.0, 1.0)
    material: Dict[str, object] = field(default_factory=dict)
    loop: bool = False


@dataclass
class HologramSession:
    session_id: str
    stage: HologramStage
    viewers: Dict[str, Viewer] = field(default_factory=dict)
    content: Dict[str, PlacedContent] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------

class HologramEngine:
    """
    Owns registered HologramStages and live HologramSessions. Coroutine-safe
    for concurrent access from websocket/control handlers serving multiple
    viewers per stage.
    """

    def __init__(self, render_pipeline: Optional[RenderPipeline] = None,
                 asset_loader: Optional[AssetLoader] = None):
        self._asset_loader = asset_loader or AssetLoader()
        self._pipeline = render_pipeline or RenderPipeline(asset_loader=self._asset_loader)
        self._stages: Dict[str, HologramStage] = {}
        self._sessions: Dict[str, HologramSession] = {}
        self._lock = asyncio.Lock()

    # -- stage registry -------------------------------------------------------

    async def register_stage(self, stage: HologramStage) -> None:
        async with self._lock:
            self._stages[stage.stage_id] = stage
        logger.info("Registered hologram stage '%s' (%s)", stage.name, stage.stage_type.value)

    def get_stage(self, stage_id: str) -> HologramStage:
        stage = self._stages.get(stage_id)
        if stage is None:
            raise StageNotFoundError(f"Unknown stage: {stage_id}")
        return stage

    def calibrate_stage(self, stage_id: str, calibration_data: Dict[str, object]) -> HologramStage:
        stage = self.get_stage(stage_id)
        if not calibration_data:
            raise StageCalibrationError(f"Empty calibration data for stage {stage_id}")
        stage.calibration_data = calibration_data
        stage.calibrated = True
        logger.info("Stage '%s' calibrated", stage.name)
        return stage

    # -- session lifecycle ------------------------------------------------------

    async def create_session(self, stage_id: str) -> HologramSession:
        stage = self.get_stage(stage_id)
        if not stage.calibrated:
            logger.warning("Starting session on uncalibrated stage '%s'; "
                            "content placement may be inaccurate", stage.name)
        session = HologramSession(session_id=uuid.uuid4().hex, stage=stage)
        async with self._lock:
            self._sessions[session.session_id] = session
        logger.info("Created hologram session %s on stage '%s'", session.session_id, stage.name)
        return session

    def get_session(self, session_id: str) -> HologramSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise HologramSessionNotFoundError(f"Unknown hologram session: {session_id}")
        return session

    async def end_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)
        logger.info("Ended hologram session %s", session_id)

    # -- viewers ----------------------------------------------------------------

    def add_viewer(self, session_id: str, viewer_id: str,
                    pose: Optional[ViewerPose] = None) -> Viewer:
        session = self.get_session(session_id)
        if len(session.viewers) >= session.stage.max_viewers:
            raise HologramEngineError(
                f"Stage '{session.stage.name}' is at capacity "
                f"({session.stage.max_viewers} viewers)"
            )
        viewer = Viewer(viewer_id=viewer_id, pose=pose or ViewerPose())
        session.viewers[viewer_id] = viewer
        logger.debug("Viewer %s added to hologram session %s", viewer_id, session_id)
        return viewer

    def remove_viewer(self, session_id: str, viewer_id: str) -> None:
        session = self.get_session(session_id)
        session.viewers.pop(viewer_id, None)

    def update_viewer_pose(self, session_id: str, viewer_id: str, pose: ViewerPose) -> Viewer:
        session = self.get_session(session_id)
        viewer = session.viewers.get(viewer_id)
        if viewer is None:
            raise ViewerNotFoundError(f"Unknown viewer: {viewer_id}")
        viewer.pose = pose
        viewer.touch()
        return viewer

    # -- content placement --------------------------------------------------------

    def place_content(self, session_id: str, asset_path: str,
                       position: Sequence[float] = (0.0, 0.0, 0.0),
                       orientation: Sequence[float] = (0.0, 0.0, 0.0, 1.0),
                       scale: Sequence[float] = (1.0, 1.0, 1.0),
                       material: Optional[Dict[str, object]] = None,
                       loop: bool = False) -> PlacedContent:
        session = self.get_session(session_id)
        if not session.stage.working_volume.contains(position):
            raise OutOfVolumeError(
                f"Position {position} is outside stage '{session.stage.name}' "
                f"working volume"
            )
        content = PlacedContent(
            content_id=uuid.uuid4().hex,
            asset_path=asset_path,
            position=position,
            orientation=orientation,
            scale=scale,
            material=material or {},
            loop=loop,
        )
        session.content[content.content_id] = content
        logger.debug("Placed content %s at %s in session %s",
                     content.content_id, position, session_id)
        return content

    def move_content(self, session_id: str, content_id: str,
                      position: Sequence[float]) -> PlacedContent:
        session = self.get_session(session_id)
        content = session.content.get(content_id)
        if content is None:
            raise ContentNotFoundError(f"Unknown content: {content_id}")
        if not session.stage.working_volume.contains(position):
            raise OutOfVolumeError(
                f"Position {position} is outside stage '{session.stage.name}' "
                f"working volume"
            )
        content.position = position
        return content

    def remove_content(self, session_id: str, content_id: str) -> None:
        session = self.get_session(session_id)
        if content_id not in session.content:
            raise ContentNotFoundError(f"Unknown content: {content_id}")
        del session.content[content_id]

    # -- rendering ----------------------------------------------------------------

    def _build_scene_objects(self, session: HologramSession) -> List[SceneObject]:
        return [
            SceneObject(
                object_id=content.content_id,
                asset_path=content.asset_path,
                transform={
                    "position": content.position,
                    "orientation": content.orientation,
                    "scale": content.scale,
                },
                material=content.material,
            )
            for content in session.content.values()
        ]

    def _build_camera_state_for_viewer(self, viewer: Viewer) -> CameraState:
        # For hologram stages the "camera" represents the viewer's eye/head
        # position relative to the stage, used to select or synthesize the
        # correct angular view rather than a conventional first-person camera.
        return CameraState(position=viewer.pose.position, orientation=viewer.pose.orientation)

    async def render_frame_for_viewer(self, session_id: str, viewer_id: str) -> FrameResult:
        session = self.get_session(session_id)
        viewer = session.viewers.get(viewer_id)
        if viewer is None:
            raise ViewerNotFoundError(f"Unknown viewer: {viewer_id}")

        try:
            return await self._pipeline.render_frame(
                session_id=f"{session_id}:{viewer_id}",
                target=RenderTarget.HOLOGRAM,
                scene_objects=self._build_scene_objects(session),
                camera=self._build_camera_state_for_viewer(viewer),
            )
        except RenderPipelineError as exc:
            logger.error("Hologram render failed for viewer %s in session %s: %s",
                         viewer_id, session_id, exc)
            raise

    async def render_frame_for_all_viewers(
        self, session_id: str
    ) -> Dict[str, Optional[FrameResult]]:
        """Renders one view per tracked viewer concurrently; a single viewer's
        render failure doesn't block the others from getting their frame."""
        session = self.get_session(session_id)

        async def _render_one(vid: str) -> Tuple[str, Optional[FrameResult]]:
            try:
                return vid, await self.render_frame_for_viewer(session_id, vid)
            except RenderPipelineError:
                return vid, None

        results = await asyncio.gather(*(_render_one(vid) for vid in session.viewers))
        return dict(results)
