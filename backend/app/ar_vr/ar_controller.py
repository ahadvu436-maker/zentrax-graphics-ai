"""
ar_controller.py
-----------------
Control layer for Augmented Reality sessions in the ZentraX backend:
device/tracking state, spatial anchors, plane detection, and driving the
render pipeline to produce AR frames anchored to the real world.

Design goals:
  - Track per-device session state (pose, tracking quality, anchors,
    detected planes) independently of rendering, so tracking updates can
    arrive at a different rate than rendered frames.
  - Treat "tracking lost" as a normal, expected state (not an exception) -
    AR tracking degrades and recovers constantly, so callers need a status
    to branch on, not a crash.
  - Anchors are the source of truth for where content is placed; scene
    objects are resolved against anchors at render time so a single anchor
    update moves everything attached to it.
  - Stays render-pipeline-agnostic about *how* frames are produced; this
    module builds the CameraState/SceneObjects and delegates rendering to
    RenderPipeline.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence

try:
    from app.graphics.render_pipeline import (
        CameraState,
        FrameResult,
        RenderPipeline,
        RenderPipelineError,
        RenderTarget,
        SceneObject,
    )
    from app.graphics.asset_loader import AssetLoader
except ImportError:  # pragma: no cover - fallback for flat/local layouts
    from render_pipeline import (
        CameraState,
        FrameResult,
        RenderPipeline,
        RenderPipelineError,
        RenderTarget,
        SceneObject,
    )
    from asset_loader import AssetLoader

logger = logging.getLogger("zentrax.ar_controller")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class ARControllerError(Exception):
    """Base class for AR-controller failures."""


class ARSessionNotFoundError(ARControllerError):
    """Raised when an operation references an unknown session_id."""


class AnchorNotFoundError(ARControllerError):
    """Raised when an operation references an unknown anchor_id."""


# --------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------

class DeviceType(str, Enum):
    PHONE = "phone"
    TABLET = "tablet"
    HEADSET = "headset"
    GLASSES = "glasses"


class TrackingState(str, Enum):
    INITIALIZING = "initializing"
    TRACKING = "tracking"
    LIMITED = "limited"     # e.g. low light, fast motion
    LOST = "lost"


class AnchorType(str, Enum):
    POINT = "point"
    PLANE = "plane"
    IMAGE = "image"
    FACE = "face"


@dataclass
class Pose:
    position: Sequence[float] = (0.0, 0.0, 0.0)
    orientation: Sequence[float] = (0.0, 0.0, 0.0, 1.0)  # quaternion (x, y, z, w)
    timestamp: float = field(default_factory=time.time)


@dataclass
class Anchor:
    anchor_id: str
    pose: Pose
    anchor_type: AnchorType
    metadata: Dict[str, object] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class DetectedPlane:
    plane_id: str
    center: Sequence[float]
    extent: Sequence[float]  # (width, height)
    normal: Sequence[float] = (0.0, 1.0, 0.0)
    updated_at: float = field(default_factory=time.time)


@dataclass
class AttachedObject:
    """A scene object anchored to a specific anchor's pose."""
    object_id: str
    anchor_id: str
    asset_path: str
    local_transform: Dict[str, object] = field(default_factory=dict)
    material: Dict[str, object] = field(default_factory=dict)


@dataclass
class ARSession:
    session_id: str
    device_id: str
    device_type: DeviceType
    tracking_state: TrackingState = TrackingState.INITIALIZING
    device_pose: Pose = field(default_factory=Pose)
    anchors: Dict[str, Anchor] = field(default_factory=dict)
    planes: Dict[str, DetectedPlane] = field(default_factory=dict)
    attached_objects: Dict[str, AttachedObject] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    stale_after_seconds: float = 30.0

    def touch(self) -> None:
        self.last_updated = time.time()

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.last_updated) > self.stale_after_seconds


# --------------------------------------------------------------------------
# Controller
# --------------------------------------------------------------------------

class ARController:
    """
    Owns all active AR sessions. One session per connected device. Thread/
    coroutine-safe for concurrent access from websocket handlers.
    """

    def __init__(self, render_pipeline: Optional[RenderPipeline] = None,
                 asset_loader: Optional[AssetLoader] = None):
        self._asset_loader = asset_loader or AssetLoader()
        self._pipeline = render_pipeline or RenderPipeline(asset_loader=self._asset_loader)
        self._sessions: Dict[str, ARSession] = {}
        self._lock = asyncio.Lock()

    # -- session lifecycle --------------------------------------------------

    async def create_session(self, device_id: str, device_type: DeviceType) -> ARSession:
        session = ARSession(
            session_id=uuid.uuid4().hex,
            device_id=device_id,
            device_type=device_type,
        )
        async with self._lock:
            self._sessions[session.session_id] = session
        logger.info("Created AR session %s for device %s (%s)",
                    session.session_id, device_id, device_type.value)
        return session

    async def end_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)
        logger.info("Ended AR session %s", session_id)

    def get_session(self, session_id: str) -> ARSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise ARSessionNotFoundError(f"Unknown AR session: {session_id}")
        return session

    async def prune_stale_sessions(self) -> List[str]:
        """Removes sessions that haven't been updated recently. Returns removed IDs."""
        async with self._lock:
            stale_ids = [sid for sid, s in self._sessions.items() if s.is_stale]
            for sid in stale_ids:
                del self._sessions[sid]
        if stale_ids:
            logger.info("Pruned %d stale AR session(s): %s", len(stale_ids), stale_ids)
        return stale_ids

    # -- tracking -------------------------------------------------------

    def update_device_pose(self, session_id: str, pose: Pose,
                            tracking_state: Optional[TrackingState] = None) -> ARSession:
        session = self.get_session(session_id)
        session.device_pose = pose
        if tracking_state is not None:
            session.tracking_state = tracking_state
        session.touch()
        return session

    def update_tracking_state(self, session_id: str, state: TrackingState) -> ARSession:
        session = self.get_session(session_id)
        if state == TrackingState.LOST and session.tracking_state != TrackingState.LOST:
            logger.warning("Tracking lost for AR session %s (device %s)",
                            session_id, session.device_id)
        session.tracking_state = state
        session.touch()
        return session

    def update_planes(self, session_id: str, planes: List[DetectedPlane]) -> ARSession:
        session = self.get_session(session_id)
        for plane in planes:
            session.planes[plane.plane_id] = plane
        session.touch()
        return session

    # -- anchors ----------------------------------------------------------

    def add_anchor(self, session_id: str, pose: Pose, anchor_type: AnchorType,
                    metadata: Optional[Dict[str, object]] = None) -> Anchor:
        session = self.get_session(session_id)
        anchor = Anchor(
            anchor_id=uuid.uuid4().hex,
            pose=pose,
            anchor_type=anchor_type,
            metadata=metadata or {},
        )
        session.anchors[anchor.anchor_id] = anchor
        session.touch()
        logger.debug("Added %s anchor %s to session %s", anchor_type.value,
                     anchor.anchor_id, session_id)
        return anchor

    def update_anchor_pose(self, session_id: str, anchor_id: str, pose: Pose) -> Anchor:
        session = self.get_session(session_id)
        anchor = session.anchors.get(anchor_id)
        if anchor is None:
            raise AnchorNotFoundError(f"Unknown anchor: {anchor_id}")
        anchor.pose = pose
        session.touch()
        return anchor

    def remove_anchor(self, session_id: str, anchor_id: str) -> None:
        session = self.get_session(session_id)
        if anchor_id not in session.anchors:
            raise AnchorNotFoundError(f"Unknown anchor: {anchor_id}")
        del session.anchors[anchor_id]
        # Detach any objects that were pinned to this anchor.
        orphaned = [oid for oid, obj in session.attached_objects.items()
                    if obj.anchor_id == anchor_id]
        for oid in orphaned:
            del session.attached_objects[oid]
        session.touch()
        if orphaned:
            logger.debug("Removed anchor %s, detached %d object(s)", anchor_id, len(orphaned))

    # -- content attachment -------------------------------------------------

    def attach_object(self, session_id: str, anchor_id: str, asset_path: str,
                       local_transform: Optional[Dict[str, object]] = None,
                       material: Optional[Dict[str, object]] = None) -> AttachedObject:
        session = self.get_session(session_id)
        if anchor_id not in session.anchors:
            raise AnchorNotFoundError(f"Cannot attach object: unknown anchor {anchor_id}")
        obj = AttachedObject(
            object_id=uuid.uuid4().hex,
            anchor_id=anchor_id,
            asset_path=asset_path,
            local_transform=local_transform or {},
            material=material or {},
        )
        session.attached_objects[obj.object_id] = obj
        session.touch()
        return obj

    def detach_object(self, session_id: str, object_id: str) -> None:
        session = self.get_session(session_id)
        session.attached_objects.pop(object_id, None)
        session.touch()

    # -- rendering ----------------------------------------------------------

    def _build_camera_state(self, session: ARSession) -> CameraState:
        return CameraState(
            position=session.device_pose.position,
            orientation=session.device_pose.orientation,
        )

    def _build_scene_objects(self, session: ARSession) -> List[SceneObject]:
        scene_objects: List[SceneObject] = []
        for obj in session.attached_objects.values():
            anchor = session.anchors.get(obj.anchor_id)
            if anchor is None:
                continue  # anchor was removed since the object was attached
            scene_objects.append(SceneObject(
                object_id=obj.object_id,
                asset_path=obj.asset_path,
                transform={
                    "anchor_position": anchor.pose.position,
                    "anchor_orientation": anchor.pose.orientation,
                    "local": obj.local_transform,
                },
                material=obj.material,
            ))
        return scene_objects

    async def render_frame(self, session_id: str) -> Optional[FrameResult]:
        """
        Renders the current AR frame for a session. Returns None (rather than
        raising) when tracking is lost, since there is no valid pose to
        render against - callers should hold the last good frame client-side.
        """
        session = self.get_session(session_id)

        if session.tracking_state == TrackingState.LOST:
            logger.debug("Skipping render for session %s: tracking lost", session_id)
            return None

        try:
            return await self._pipeline.render_frame(
                session_id=session_id,
                target=RenderTarget.AR,
                scene_objects=self._build_scene_objects(session),
                camera=self._build_camera_state(session),
            )
        except RenderPipelineError as exc:
            logger.error("AR render failed for session %s: %s", session_id, exc)
            raise
