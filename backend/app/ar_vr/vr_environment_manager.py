"""
vr_environment_manager.py
--------------------------
Manages Virtual Reality environments and multi-user sessions for the
ZentraX backend: registering/loading environments, tracking players inside
a shared space, handling locomotion (teleport / smooth / room-scale), and
driving the render pipeline to produce a per-player VR frame.

Design goals:
  - Separate the *environment* (a reusable, loadable scene definition) from
    a *session* (a live instance of players inside that environment), so
    one environment can back many concurrent sessions.
  - Bounds/collision checks for locomotion live here, not in the renderer,
    since they're gameplay/physics concerns, not rendering concerns.
  - Each player gets their own camera and therefore their own rendered
    frame, but all players in a session share the same environment scene
    graph plus every other player's avatar.
  - Environment loading is async and asset-heavy, so it's preloaded once
    per environment (not per player) via AssetLoader's cache.
"""

from __future__ import annotations

import asyncio
import logging
import math
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

logger = logging.getLogger("zentrax.vr_environment_manager")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class VREnvironmentError(Exception):
    """Base class for VR environment/session failures."""


class EnvironmentNotFoundError(VREnvironmentError):
    """Raised when referencing an unregistered environment_id."""


class VRSessionNotFoundError(VREnvironmentError):
    """Raised when referencing an unknown VR session_id."""


class PlayerNotFoundError(VREnvironmentError):
    """Raised when referencing a player not present in a session."""


class OutOfBoundsError(VREnvironmentError):
    """Raised when a locomotion request would move a player outside bounds."""


class EnvironmentLoadError(VREnvironmentError):
    """Raised when an environment's assets fail to preload."""


# --------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------

class LocomotionMode(str, Enum):
    TELEPORT = "teleport"
    SMOOTH = "smooth"
    ROOM_SCALE = "room_scale"


@dataclass
class Bounds:
    """Axis-aligned horizontal play bounds (min/max on X and Z)."""
    min_x: float
    max_x: float
    min_z: float
    max_z: float

    def contains(self, position: Sequence[float]) -> bool:
        x, _y, z = position[0], position[1], position[2]
        return self.min_x <= x <= self.max_x and self.min_z <= z <= self.max_z


@dataclass
class VREnvironment:
    """A reusable, loadable environment definition."""
    environment_id: str
    name: str
    scene_asset_paths: List[str]
    bounds: Bounds
    spawn_points: List[Sequence[float]] = field(default_factory=lambda: [(0.0, 0.0, 0.0)])
    static_objects: List[SceneObject] = field(default_factory=list)
    loaded: bool = False


@dataclass
class PlayerState:
    player_id: str
    position: Sequence[float] = (0.0, 0.0, 0.0)
    orientation: Sequence[float] = (0.0, 0.0, 0.0, 1.0)
    velocity: Sequence[float] = (0.0, 0.0, 0.0)
    avatar_asset_path: Optional[str] = None
    locomotion_mode: LocomotionMode = LocomotionMode.TELEPORT
    joined_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_updated = time.time()


@dataclass
class VRSession:
    session_id: str
    environment: VREnvironment
    players: Dict[str, PlayerState] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def next_spawn_point(self) -> Sequence[float]:
        idx = len(self.players) % len(self.environment.spawn_points)
        return self.environment.spawn_points[idx]


# --------------------------------------------------------------------------
# Manager
# --------------------------------------------------------------------------

class VREnvironmentManager:
    """
    Owns registered VREnvironments and live VRSessions. Coroutine-safe for
    concurrent access from websocket handlers serving multiple players.
    """

    # Maximum distance a single smooth-locomotion update may move a player,
    # as a basic anti-cheat / sanity guard against malformed client input.
    MAX_SMOOTH_STEP_METERS = 5.0

    def __init__(self, render_pipeline: Optional[RenderPipeline] = None,
                 asset_loader: Optional[AssetLoader] = None):
        self._asset_loader = asset_loader or AssetLoader()
        self._pipeline = render_pipeline or RenderPipeline(asset_loader=self._asset_loader)
        self._environments: Dict[str, VREnvironment] = {}
        self._sessions: Dict[str, VRSession] = {}
        self._lock = asyncio.Lock()

    # -- environment registry ------------------------------------------------

    async def register_environment(self, environment: VREnvironment) -> None:
        async with self._lock:
            self._environments[environment.environment_id] = environment
        logger.info("Registered VR environment '%s' (%s)",
                    environment.name, environment.environment_id)

    def get_environment(self, environment_id: str) -> VREnvironment:
        env = self._environments.get(environment_id)
        if env is None:
            raise EnvironmentNotFoundError(f"Unknown environment: {environment_id}")
        return env

    async def preload_environment(self, environment_id: str) -> VREnvironment:
        """Warms the asset cache for an environment's assets ahead of use."""
        env = self.get_environment(environment_id)
        if env.loaded:
            return env
        try:
            await self._asset_loader.preload(env.scene_asset_paths)
        except AssetError as exc:
            raise EnvironmentLoadError(
                f"Failed to preload environment '{environment_id}': {exc}"
            ) from exc
        env.loaded = True
        logger.info("Preloaded %d asset(s) for environment '%s'",
                    len(env.scene_asset_paths), environment_id)
        return env

    # -- session lifecycle ----------------------------------------------------

    async def create_session(self, environment_id: str) -> VRSession:
        env = await self.preload_environment(environment_id)
        session = VRSession(session_id=uuid.uuid4().hex, environment=env)
        async with self._lock:
            self._sessions[session.session_id] = session
        logger.info("Created VR session %s in environment '%s'", session.session_id, env.name)
        return session

    def get_session(self, session_id: str) -> VRSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise VRSessionNotFoundError(f"Unknown VR session: {session_id}")
        return session

    async def end_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)
        logger.info("Ended VR session %s", session_id)

    # -- players --------------------------------------------------------------

    def join_session(self, session_id: str, player_id: str,
                      avatar_asset_path: Optional[str] = None) -> PlayerState:
        session = self.get_session(session_id)
        player = PlayerState(
            player_id=player_id,
            position=session.next_spawn_point(),
            avatar_asset_path=avatar_asset_path,
        )
        session.players[player_id] = player
        logger.info("Player %s joined VR session %s at %s",
                    player_id, session_id, player.position)
        return player

    def leave_session(self, session_id: str, player_id: str) -> None:
        session = self.get_session(session_id)
        session.players.pop(player_id, None)
        logger.info("Player %s left VR session %s", player_id, session_id)

    def _get_player(self, session: VRSession, player_id: str) -> PlayerState:
        player = session.players.get(player_id)
        if player is None:
            raise PlayerNotFoundError(f"Unknown player: {player_id}")
        return player

    # -- locomotion -----------------------------------------------------------

    def teleport(self, session_id: str, player_id: str, target_position: Sequence[float]) -> PlayerState:
        session = self.get_session(session_id)
        player = self._get_player(session, player_id)
        if not session.environment.bounds.contains(target_position):
            raise OutOfBoundsError(f"Teleport target {target_position} is outside environment bounds")
        player.position = target_position
        player.velocity = (0.0, 0.0, 0.0)
        player.locomotion_mode = LocomotionMode.TELEPORT
        player.touch()
        return player

    def move_smooth(self, session_id: str, player_id: str,
                     delta: Sequence[float]) -> PlayerState:
        """Applies an incremental move, clamped to the environment bounds."""
        session = self.get_session(session_id)
        player = self._get_player(session, player_id)

        step_distance = math.sqrt(sum(d * d for d in delta))
        if step_distance > self.MAX_SMOOTH_STEP_METERS:
            raise VREnvironmentError(
                f"Rejected implausible move of {step_distance:.2f}m in one update"
            )

        proposed = tuple(p + d for p, d in zip(player.position, delta))
        bounds = session.environment.bounds
        clamped = (
            min(max(proposed[0], bounds.min_x), bounds.max_x),
            proposed[1],
            min(max(proposed[2], bounds.min_z), bounds.max_z),
        )
        player.position = clamped
        player.locomotion_mode = LocomotionMode.SMOOTH
        player.touch()
        return player

    def update_orientation(self, session_id: str, player_id: str,
                            orientation: Sequence[float]) -> PlayerState:
        session = self.get_session(session_id)
        player = self._get_player(session, player_id)
        player.orientation = orientation
        player.touch()
        return player

    # -- rendering --------------------------------------------------------------

    def _build_scene_objects(self, session: VRSession, viewer_id: str) -> List[SceneObject]:
        scene_objects: List[SceneObject] = list(session.environment.static_objects)

        for player_id, player in session.players.items():
            if player_id == viewer_id or not player.avatar_asset_path:
                continue  # don't render the viewer's own avatar into their own view
            scene_objects.append(SceneObject(
                object_id=f"avatar_{player_id}",
                asset_path=player.avatar_asset_path,
                transform={
                    "position": player.position,
                    "orientation": player.orientation,
                },
            ))
        return scene_objects

    async def render_frame_for_player(self, session_id: str, player_id: str) -> FrameResult:
        session = self.get_session(session_id)
        player = self._get_player(session, player_id)

        camera = CameraState(position=player.position, orientation=player.orientation)
        scene_objects = self._build_scene_objects(session, viewer_id=player_id)

        try:
            return await self._pipeline.render_frame(
                session_id=f"{session_id}:{player_id}",
                target=RenderTarget.VR,
                scene_objects=scene_objects,
                camera=camera,
            )
        except RenderPipelineError as exc:
            logger.error("VR render failed for player %s in session %s: %s",
                         player_id, session_id, exc)
            raise

    async def render_frame_for_all(self, session_id: str) -> Dict[str, Optional[FrameResult]]:
        """Renders one frame per player concurrently; a single player's render
        failure doesn't take down the others."""
        session = self.get_session(session_id)

        async def _render_one(pid: str) -> Tuple[str, Optional[FrameResult]]:
            try:
                return pid, await self.render_frame_for_player(session_id, pid)
            except RenderPipelineError:
                return pid, None

        results = await asyncio.gather(*(_render_one(pid) for pid in session.players))
        return dict(results)
