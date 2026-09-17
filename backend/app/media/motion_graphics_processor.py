"""
motion_graphics_processor.py

Utilities for applying motion graphics to video files:
- Animated text overlays (fade, slide, typewriter, scale)
- Transition effects between clips (crossfade, wipe, slide)
- Simple kinetic effects (zoom/pan - "Ken Burns", shake, pulse)
- Lower-third / caption bar generation

Built on moviepy (video composition) and numpy/PIL for frame-level effects.

Install:
    pip install moviepy pillow numpy --break-system-packages

Usage example (see bottom of file for a runnable __main__ demo):

    from motion_graphics_processor import MotionGraphicsProcessor

    mgp = MotionGraphicsProcessor()
    clip = mgp.add_animated_text(
        "input.mp4", "Hello World!", start=1.0, duration=3.0,
        animation="slide_up", position="bottom"
    )
    mgp.export(clip, "output.mp4")
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple, Union

import numpy as np

try:
    from moviepy.editor import (
        VideoFileClip,
        VideoClip,
        TextClip,
        CompositeVideoClip,
        ImageClip,
        concatenate_videoclips,
        vfx,
    )
except ImportError as e:
    raise ImportError(
        "moviepy is required. Install with: "
        "pip install moviepy pillow numpy --break-system-packages"
    ) from e


Number = Union[int, float]


# --------------------------------------------------------------------------
# Easing functions - used to drive animation curves smoothly
# --------------------------------------------------------------------------

def ease_linear(t: float) -> float:
    return t


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4 * t ** 3
    return 1 - ((-2 * t + 2) ** 3) / 2


def ease_out_back(t: float, overshoot: float = 1.70158) -> float:
    c1 = overshoot
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


EASINGS = {
    "linear": ease_linear,
    "ease_in_out": ease_in_out_cubic,
    "ease_out_back": ease_out_back,
}


@dataclass
class TextStyle:
    font: str = "DejaVu-Sans-Bold"
    fontsize: int = 60
    color: str = "white"
    stroke_color: Optional[str] = "black"
    stroke_width: int = 2
    bg_color: Optional[str] = None  # e.g. "rgba(0,0,0,0.5)" not supported by TextClip; use bar helper instead


class MotionGraphicsProcessor:
    """
    High-level API for adding motion graphics to a video clip.

    Most methods accept either a file path (str) or an already-loaded
    moviepy VideoClip and return a moviepy VideoClip so calls can be chained.
    """

    def __init__(self, default_fps: int = 30):
        self.default_fps = default_fps

    # ------------------------------------------------------------------
    # Loading / exporting
    # ------------------------------------------------------------------

    def _load(self, source: Union[str, VideoClip]) -> VideoClip:
        if isinstance(source, str):
            return VideoFileClip(source)
        return source

    def export(
        self,
        clip: VideoClip,
        output_path: str,
        fps: Optional[int] = None,
        codec: str = "libx264",
        audio_codec: str = "aac",
        bitrate: Optional[str] = None,
        threads: int = 4,
    ) -> str:
        """Render the final clip to disk."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        clip.write_videofile(
            output_path,
            fps=fps or getattr(clip, "fps", None) or self.default_fps,
            codec=codec,
            audio_codec=audio_codec,
            bitrate=bitrate,
            threads=threads,
            logger=None,
        )
        return output_path

    # ------------------------------------------------------------------
    # Animated text overlays
    # ------------------------------------------------------------------

    def add_animated_text(
        self,
        source: Union[str, VideoClip],
        text: str,
        start: float = 0.0,
        duration: float = 3.0,
        animation: str = "fade",  # fade | slide_up | slide_down | slide_left | slide_right | scale_in | typewriter
        position: Union[str, Tuple[Number, Number]] = "bottom",
        style: Optional[TextStyle] = None,
        easing: str = "ease_in_out",
        anim_time: float = 0.5,
    ) -> VideoClip:
        """
        Overlay animated text onto a video.

        `animation` controls how the text enters/exits.
        `anim_time` is how long the enter/exit transition itself takes (seconds).
        """
        base = self._load(source)
        style = style or TextStyle()
        ease_fn = EASINGS.get(easing, ease_in_out_cubic)

        txt_clip = TextClip(
            text,
            fontsize=style.fontsize,
            color=style.color,
            font=style.font,
            stroke_color=style.stroke_color,
            stroke_width=style.stroke_width,
        ).set_duration(duration)

        w, h = base.size
        tw, th = txt_clip.size

        base_pos = self._resolve_position(position, w, h, tw, th)

        if animation == "fade":
            txt_clip = txt_clip.crossfadein(anim_time).crossfadeout(anim_time)
            txt_clip = txt_clip.set_position(base_pos)

        elif animation in ("slide_up", "slide_down", "slide_left", "slide_right"):
            txt_clip = txt_clip.set_position(
                self._slide_position_fn(animation, base_pos, duration, anim_time, ease_fn, w, h, tw, th)
            )

        elif animation == "scale_in":
            def resize_fn(t):
                if t < anim_time:
                    return max(0.01, ease_fn(t / anim_time))
                return 1.0
            txt_clip = txt_clip.resize(resize_fn).set_position(base_pos)

        elif animation == "typewriter":
            txt_clip = self._typewriter_clip(text, duration, style, base_pos)

        else:
            raise ValueError(f"Unknown animation type: {animation}")

        txt_clip = txt_clip.set_start(start)
        return CompositeVideoClip([base, txt_clip])

    def _resolve_position(
        self, position: Union[str, Tuple[Number, Number]], w: int, h: int, tw: int, th: int
    ) -> Tuple[Number, Number]:
        margin = 40
        presets = {
            "top": ("center", margin),
            "bottom": ("center", h - th - margin),
            "center": ("center", "center"),
            "top_left": (margin, margin),
            "top_right": (w - tw - margin, margin),
            "bottom_left": (margin, h - th - margin),
            "bottom_right": (w - tw - margin, h - th - margin),
        }
        if isinstance(position, str):
            return presets.get(position, presets["bottom"])
        return position

    def _slide_position_fn(
        self, animation: str, base_pos, duration: float, anim_time: float,
        ease_fn: Callable[[float], float], w: int, h: int, tw: int, th: int
    ) -> Callable[[float], Tuple[Number, Number]]:
        bx, by = base_pos
        bx_val = w / 2 - tw / 2 if bx == "center" else bx
        by_val = h / 2 - th / 2 if by == "center" else by

        offsets = {
            "slide_up": (0, th + 60),
            "slide_down": (0, -(th + 60)),
            "slide_left": (tw + 60, 0),
            "slide_right": (-(tw + 60), 0),
        }
        off_x, off_y = offsets[animation]

        def pos_fn(t: float) -> Tuple[Number, Number]:
            # entrance
            if t < anim_time:
                p = ease_fn(t / anim_time)
                return (bx_val + off_x * (1 - p), by_val + off_y * (1 - p))
            # exit
            if t > duration - anim_time:
                p = ease_fn((t - (duration - anim_time)) / anim_time)
                return (bx_val + off_x * p, by_val + off_y * p)
            return (bx_val, by_val)

        return pos_fn

    def _typewriter_clip(
        self, text: str, duration: float, style: TextStyle, base_pos
    ) -> VideoClip:
        """Reveal text character-by-character over the clip duration."""
        n_chars = max(len(text), 1)
        chars_per_sec = n_chars / max(duration * 0.8, 0.1)  # finish reveal at 80% of duration

        def make_frame_text(t: float) -> str:
            n_visible = min(n_chars, int(t * chars_per_sec))
            return text[:n_visible] if n_visible > 0 else " "

        # moviepy TextClip isn't natively time-varying, so we build a VideoClip
        # that renders a fresh TextClip frame at each timestep.
        cache = {}

        def make_frame(t):
            visible = make_frame_text(t)
            if visible not in cache:
                tc = TextClip(
                    visible,
                    fontsize=style.fontsize,
                    color=style.color,
                    font=style.font,
                    stroke_color=style.stroke_color,
                    stroke_width=style.stroke_width,
                )
                cache[visible] = tc.get_frame(0), tc.size
            frame, _ = cache[visible]
            return frame

        clip = VideoClip(make_frame, duration=duration)
        clip = clip.set_position(base_pos)
        return clip

    # ------------------------------------------------------------------
    # Transitions between clips
    # ------------------------------------------------------------------

    def crossfade_transition(
        self, clip_a: Union[str, VideoClip], clip_b: Union[str, VideoClip], overlap: float = 1.0
    ) -> VideoClip:
        """Concatenate two clips with a crossfade dissolve between them."""
        a = self._load(clip_a)
        b = self._load(clip_b).crossfadein(overlap)
        return concatenate_videoclips(
            [a, b.set_start(a.duration - overlap)], padding=-overlap, method="compose"
        )

    def slide_transition(
        self,
        clip_a: Union[str, VideoClip],
        clip_b: Union[str, VideoClip],
        duration: float = 1.0,
        direction: str = "left",  # left | right | up | down
    ) -> VideoClip:
        """Slide clip_b in over clip_a to replace it."""
        a = self._load(clip_a)
        b = self._load(clip_b)
        w, h = a.size

        vectors = {
            "left": (w, 0),
            "right": (-w, 0),
            "up": (0, h),
            "down": (0, -h),
        }
        dx, dy = vectors[direction]

        def b_position(t):
            if t >= duration:
                return (0, 0)
            p = ease_in_out_cubic(t / duration)
            return (dx * (1 - p), dy * (1 - p))

        transition_start = max(0, a.duration - duration)
        b_during = b.subclip(0, min(duration, b.duration)).set_position(b_position).set_start(transition_start)
        b_after = None
        if b.duration > duration:
            b_after = b.subclip(duration).set_start(transition_start + duration)

        layers = [a, b_during]
        if b_after is not None:
            layers.append(b_after)
        composite = CompositeVideoClip(layers, size=(w, h))
        composite = composite.set_duration(transition_start + b.duration)
        return composite

    # ------------------------------------------------------------------
    # Kinetic effects
    # ------------------------------------------------------------------

    def ken_burns(
        self,
        source: Union[str, VideoClip],
        zoom_start: float = 1.0,
        zoom_end: float = 1.15,
        pan: Tuple[Number, Number] = (0, 0),
        duration: Optional[float] = None,
    ) -> VideoClip:
        """Slow pan-and-zoom effect, classic for still images or B-roll."""
        clip = self._load(source)
        duration = duration or clip.duration

        def resize_fn(t):
            p = t / duration
            return zoom_start + (zoom_end - zoom_start) * p

        def pos_fn(t):
            p = t / duration
            return (pan[0] * p, pan[1] * p)

        return clip.resize(resize_fn).set_position(pos_fn)

    def shake(
        self, source: Union[str, VideoClip], intensity: float = 8.0, frequency: float = 12.0
    ) -> VideoClip:
        """Camera-shake effect using sinusoidal jitter."""
        clip = self._load(source)

        def pos_fn(t):
            x = intensity * math.sin(t * frequency * 2 * math.pi)
            y = intensity * math.cos(t * frequency * 1.7 * math.pi)
            return (x, y)

        return clip.set_position(pos_fn)

    def pulse(
        self, source: Union[str, VideoClip], intensity: float = 0.05, frequency: float = 2.0
    ) -> VideoClip:
        """Subtle scale pulsing, e.g. to emphasize a beat or logo."""
        clip = self._load(source)

        def resize_fn(t):
            return 1.0 + intensity * math.sin(t * frequency * 2 * math.pi)

        return clip.resize(resize_fn)

    # ------------------------------------------------------------------
    # Lower thirds / caption bars
    # ------------------------------------------------------------------

    def lower_third(
        self,
        source: Union[str, VideoClip],
        title: str,
        subtitle: str = "",
        start: float = 0.0,
        duration: float = 4.0,
        bar_color: Tuple[int, int, int] = (20, 20, 20),
        bar_opacity: float = 0.75,
        text_color: str = "white",
    ) -> VideoClip:
        """Broadcast-style lower-third with a solid bar and slide-in animation."""
        base = self._load(source)
        w, h = base.size
        bar_h = int(h * 0.14)
        bar_y = h - bar_h - int(h * 0.08)

        bar_frame = np.zeros((bar_h, w, 3), dtype=np.uint8)
        bar_frame[:, :] = bar_color
        bar_clip = (
            ImageClip(bar_frame)
            .set_duration(duration)
            .set_opacity(bar_opacity)
        )

        def bar_pos(t):
            anim_time = 0.4
            if t < anim_time:
                p = ease_in_out_cubic(t / anim_time)
                return (-w * (1 - p) * 0.3, bar_y)
            return (0, bar_y)

        bar_clip = bar_clip.set_position(bar_pos).set_start(start)

        title_clip = (
            TextClip(title, fontsize=int(bar_h * 0.45), color=text_color, font="DejaVu-Sans-Bold")
            .set_duration(duration)
            .set_position((int(w * 0.03), bar_y + int(bar_h * 0.08)))
            .set_start(start + 0.1)
            .crossfadein(0.3)
        )

        layers = [base, bar_clip, title_clip]

        if subtitle:
            subtitle_clip = (
                TextClip(subtitle, fontsize=int(bar_h * 0.28), color=text_color, font="DejaVu-Sans")
                .set_duration(duration)
                .set_position((int(w * 0.03), bar_y + int(bar_h * 0.55)))
                .set_start(start + 0.15)
                .crossfadein(0.3)
            )
            layers.append(subtitle_clip)

        return CompositeVideoClip(layers)


# --------------------------------------------------------------------------
# Demo / CLI usage
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Apply motion graphics to a video.")
    parser.add_argument("input", help="Path to input video file")
    parser.add_argument("output", help="Path to output video file")
    parser.add_argument("--text", default="Hello World", help="Overlay text")
    parser.add_argument(
        "--animation",
        default="slide_up",
        choices=["fade", "slide_up", "slide_down", "slide_left", "slide_right", "scale_in", "typewriter"],
    )
    parser.add_argument("--start", type=float, default=0.5)
    parser.add_argument("--duration", type=float, default=3.0)
    args = parser.parse_args()

    mgp = MotionGraphicsProcessor()
    result = mgp.add_animated_text(
        args.input, args.text, start=args.start, duration=args.duration, animation=args.animation
    )
    mgp.export(result, args.output)
    print(f"Wrote {args.output}")
