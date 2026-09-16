"""
realtime_stream.py
-------------------
Real-time WebSocket streaming for live 3D/AR/VR content delivery in the
ZentraX backend. Sits on top of render_pipeline.py: clients push scene/
camera updates over a websocket, and this module drives the render pipeline
at a target frame rate and streams results back.

Design goals:
  - One session per websocket connection, tracked by a ConnectionManager so
    the server can broadcast, inspect, or forcibly disconnect sessions.
  - A small JSON control protocol (subscribe/camera_update/scene_update/
    ping) kept separate from the binary/JSON frame payloads pushed to the
    client, so control and data planes don't collide.
  - Backpressure-aware sending: if a client can't keep up, we drop frames
    for that client rather than growing an unbounded queue or blocking
    other sessions.
  - Clean lifecycle handling so a client disconnecting or erroring never
    takes down the server or leaks tasks/resources.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from asset_loader import AssetLoader
from render_pipeline import (
    CameraState,
    RenderPipeline,
    RenderPipelineError,
    RenderTarget,
    SceneObject,
)

logger = logging.getLogger("zentrax.realtime_stream")

router = APIRouter()


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class StreamProtocolError(Exception):
    """Raised when a client sends a malformed or unexpected control message."""


# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------

@dataclass
class StreamSession:
    session_id: str
    websocket: WebSocket
    target: RenderTarget = RenderTarget.AR
    scene_objects: list = field(default_factory=list)
    camera: CameraState = field(default_factory=CameraState)
    target_fps: float = 30.0
    connected_at: float = field(default_factory=time.time)
    frames_sent: int = 0
    frames_dropped: int = 0
    last_error: Optional[str] = None
    _send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def update_scene(self, scene_objects: list) -> None:
        self.scene_objects = scene_objects

    def update_camera(self, camera: CameraState) -> None:
        self.camera = camera


class ConnectionManager:
    """Tracks active StreamSessions and provides safe send/broadcast helpers."""

    def __init__(self):
        self._sessions: Dict[str, StreamSession] = {}
        self._lock = asyncio.Lock()

    async def register(self, session: StreamSession) -> None:
        async with self._lock:
            self._sessions[session.session_id] = session
        logger.info("Session %s connected (target=%s)", session.session_id, session.target)

    async def unregister(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)
        logger.info("Session %s disconnected", session_id)

    def get(self, session_id: str) -> Optional[StreamSession]:
        return self._sessions.get(session_id)

    async def send_json_safe(self, session: StreamSession, payload: Dict[str, Any]) -> bool:
        """
        Sends JSON to a client, tolerating a client that is slow or gone.
        Returns False (and does not raise) if the send could not complete.
        """
        if session.websocket.application_state != WebSocketState.CONNECTED:
            return False
        try:
            async with session._send_lock:
                await session.websocket.send_json(payload)
            return True
        except Exception as exc:
            session.last_error = str(exc)
            logger.warning("Failed to send to session %s: %s", session.session_id, exc)
            return False

    @property
    def active_session_count(self) -> int:
        return len(self._sessions)


manager = ConnectionManager()


# --------------------------------------------------------------------------
# Control-message parsing
# --------------------------------------------------------------------------

def _parse_scene_objects(raw: list) -> list:
    try:
        return [
            SceneObject(
                object_id=str(item["object_id"]),
                asset_path=str(item["asset_path"]),
                transform=item.get("transform", {}),
                material=item.get("material", {}),
            )
            for item in raw
        ]
    except (KeyError, TypeError) as exc:
        raise StreamProtocolError(f"Invalid scene_objects payload: {exc}") from exc


def _parse_camera(raw: dict) -> CameraState:
    try:
        return CameraState(
            position=tuple(raw.get("position", (0.0, 0.0, 0.0))),
            orientation=tuple(raw.get("orientation", (0.0, 0.0, 0.0, 1.0))),
            fov_degrees=float(raw.get("fov_degrees", 60.0)),
        )
    except (TypeError, ValueError) as exc:
        raise StreamProtocolError(f"Invalid camera payload: {exc}") from exc


async def _handle_control_message(session: StreamSession, message: Dict[str, Any]) -> None:
    msg_type = message.get("type")

    if msg_type == "scene_update":
        session.update_scene(_parse_scene_objects(message.get("scene_objects", [])))
    elif msg_type == "camera_update":
        session.update_camera(_parse_camera(message.get("camera", {})))
    elif msg_type == "configure":
        if "target" in message:
            try:
                session.target = RenderTarget(message["target"])
            except ValueError as exc:
                raise StreamProtocolError(f"Unknown render target: {message['target']}") from exc
        if "target_fps" in message:
            fps = float(message["target_fps"])
            if not (1.0 <= fps <= 120.0):
                raise StreamProtocolError("target_fps must be between 1 and 120")
            session.target_fps = fps
    elif msg_type == "ping":
        await manager.send_json_safe(session, {"type": "pong", "t": time.time()})
    else:
        raise StreamProtocolError(f"Unknown message type: {msg_type!r}")


# --------------------------------------------------------------------------
# Frame production loop
# --------------------------------------------------------------------------

async def _frame_producer_loop(session: StreamSession, pipeline: RenderPipeline) -> None:
    """
    Runs alongside the receive loop for a session, rendering and pushing
    frames at session.target_fps. Skips a frame's render if the session has
    no scene objects yet, and drops (rather than queues) frames the socket
    can't accept quickly, to avoid unbounded latency growth.
    """
    while True:
        frame_start = time.perf_counter()

        if session.websocket.application_state != WebSocketState.CONNECTED:
            return

        if session.scene_objects:
            try:
                result = await pipeline.render_frame(
                    session_id=session.session_id,
                    target=session.target,
                    scene_objects=session.scene_objects,
                    camera=session.camera,
                )
                sent = await manager.send_json_safe(
                    session,
                    {
                        "type": "frame",
                        "frame_id": result.frame_id,
                        "output": result.output,
                        "timing_ms": result.total_time_ms,
                        "warnings": result.warnings,
                    },
                )
                if sent:
                    session.frames_sent += 1
                else:
                    session.frames_dropped += 1
            except RenderPipelineError as exc:
                session.last_error = str(exc)
                logger.error("Render error for session %s: %s", session.session_id, exc)
                await manager.send_json_safe(
                    session, {"type": "error", "message": "render_failed", "detail": str(exc)}
                )

        elapsed = time.perf_counter() - frame_start
        target_interval = 1.0 / session.target_fps if session.target_fps > 0 else 1.0 / 30.0
        sleep_for = max(0.0, target_interval - elapsed)
        await asyncio.sleep(sleep_for)


# --------------------------------------------------------------------------
# WebSocket endpoint
# --------------------------------------------------------------------------

def create_router(asset_loader: Optional[AssetLoader] = None) -> APIRouter:
    """
    Factory so the app can inject a shared AssetLoader (and therefore a
    shared cache) rather than each session spinning up its own.
    """
    pipeline = RenderPipeline(asset_loader=asset_loader or AssetLoader())

    @router.websocket("/ws/stream/{session_id}")
    async def stream_endpoint(websocket: WebSocket, session_id: str):
        await websocket.accept()
        session = StreamSession(session_id=session_id, websocket=websocket)
        await manager.register(session)

        producer_task = asyncio.create_task(_frame_producer_loop(session, pipeline))

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await manager.send_json_safe(
                        session, {"type": "error", "message": "invalid_json"}
                    )
                    continue

                try:
                    await _handle_control_message(session, message)
                except StreamProtocolError as exc:
                    await manager.send_json_safe(
                        session, {"type": "error", "message": "protocol_error", "detail": str(exc)}
                    )

        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.exception("Unexpected error in stream session %s", session_id)
            session.last_error = str(exc)
        finally:
            producer_task.cancel()
            try:
                await producer_task
            except asyncio.CancelledError:
                pass
            await manager.unregister(session_id)

    @router.get("/stream/sessions/count")
    async def session_count() -> Dict[str, int]:
        return {"active_sessions": manager.active_session_count}

    return router

