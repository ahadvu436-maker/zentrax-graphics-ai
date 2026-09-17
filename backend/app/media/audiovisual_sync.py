"""
audiovisual_sync.py

Utilities for detecting and correcting audio/video sync drift:
- Cross-correlation based offset detection between two audio tracks
  (e.g. a video's embedded audio vs. a separately recorded high-quality track)
- Applying a time-shift correction to realign audio and video
- Detecting drift that changes over time (linear clock drift) via
  windowed cross-correlation and slope fitting
- Simple "clap"/transient detection to help find sync points manually

Built on moviepy (container demux/mux), numpy, and scipy (correlation, resampling).

Install:
    pip install moviepy scipy numpy --break-system-packages

Usage example:

    from audiovisual_sync import AudioVisualSync

    avs = AudioVisualSync()
    offset = avs.detect_offset("video.mp4", "external_audio.wav")
    print(f"Detected offset: {offset:.3f}s")
    avs.apply_sync("video.mp4", "external_audio.wav", "synced_output.mp4", offset=offset)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

import numpy as np

try:
    from scipy.signal import correlate, resample
    from scipy.io import wavfile
except ImportError as e:
    raise ImportError("scipy is required. Install with: pip install scipy --break-system-packages") from e

try:
    from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip
except ImportError as e:
    raise ImportError("moviepy is required. Install with: pip install moviepy --break-system-packages") from e


@dataclass
class SyncResult:
    offset_seconds: float          # positive = audio_b lags audio_a (delay audio_b to match)
    confidence: float              # normalized correlation peak, 0-1ish
    sample_rate: int


@dataclass
class DriftResult:
    offsets: List[Tuple[float, float]]  # (timestamp, offset_seconds) pairs across windows
    drift_rate: float                    # seconds of drift per second of playback (slope)
    intercept: float                     # offset at t=0


class AudioVisualSync:
    """
    High-level API for detecting and correcting audio/video sync issues.
    """

    def __init__(self, target_sample_rate: int = 44100):
        self.sr = target_sample_rate

    # ------------------------------------------------------------------
    # Audio extraction / loading
    # ------------------------------------------------------------------

    def _extract_audio_array(self, source: Union[str, "np.ndarray"]) -> Tuple[np.ndarray, int]:
        """
        Load audio as a mono float32 numpy array + sample rate.
        Accepts a video file, an audio file, or a raw (array, sr) tuple.
        """
        if isinstance(source, tuple):
            audio, sr = source
            return self._to_mono(audio), sr

        if not isinstance(source, str):
            raise TypeError("source must be a file path or (array, sr) tuple")

        ext = os.path.splitext(source)[1].lower()

        if ext in (".wav",):
            sr, audio = wavfile.read(source)
            audio = audio.astype(np.float32)
            if audio.max() > 1.0 or audio.min() < -1.0:
                audio /= np.iinfo(np.int16).max if audio.dtype != np.float32 else 1.0
            return self._to_mono(audio), sr

        # Video or other audio containers - use moviepy/ffmpeg
        clip = VideoFileClip(source) if ext in (".mp4", ".mov", ".mkv", ".avi", ".webm") else AudioFileClip(source)
        audio_clip = clip.audio if hasattr(clip, "audio") else clip
        if audio_clip is None:
            raise ValueError(f"No audio track found in {source}")

        fps = audio_clip.fps or self.sr
        arr = audio_clip.to_soundarray(fps=fps)
        clip.close()
        return self._to_mono(arr), fps

    @staticmethod
    def _to_mono(audio: np.ndarray) -> np.ndarray:
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32)

    def _resample_to_common_rate(
        self, a: np.ndarray, sr_a: int, b: np.ndarray, sr_b: int
    ) -> Tuple[np.ndarray, np.ndarray, int]:
        target_sr = self.sr
        if sr_a != target_sr:
            a = resample(a, int(len(a) * target_sr / sr_a))
        if sr_b != target_sr:
            b = resample(b, int(len(b) * target_sr / sr_b))
        return a, b, target_sr

    # ------------------------------------------------------------------
    # Offset detection
    # ------------------------------------------------------------------

    def detect_offset(
        self,
        source_a: Union[str, "np.ndarray"],
        source_b: Union[str, "np.ndarray"],
        max_offset_seconds: Optional[float] = None,
    ) -> float:
        """
        Detect the time offset of source_b relative to source_a using
        normalized cross-correlation.

        Returns offset in seconds. Positive means source_b lags behind
        source_a (i.e. source_b's audio happens later) -- delay source_b
        to align, or advance source_a.
        """
        result = self.detect_offset_detailed(source_a, source_b, max_offset_seconds)
        return result.offset_seconds

    def detect_offset_detailed(
        self,
        source_a: Union[str, "np.ndarray"],
        source_b: Union[str, "np.ndarray"],
        max_offset_seconds: Optional[float] = None,
    ) -> SyncResult:
        a_audio, sr_a = self._extract_audio_array(source_a)
        b_audio, sr_b = self._extract_audio_array(source_b)
        a_audio, b_audio, sr = self._resample_to_common_rate(a_audio, sr_a, b_audio, sr_b)

        # Normalize to reduce amplitude-driven bias in correlation
        a_norm = self._normalize(a_audio)
        b_norm = self._normalize(b_audio)

        if max_offset_seconds is not None:
            max_lag = int(max_offset_seconds * sr)
            corr = self._bounded_correlate(a_norm, b_norm, max_lag)
            lags = np.arange(-max_lag, max_lag + 1)
        else:
            corr = correlate(a_norm, b_norm, mode="full", method="fft")
            lags = np.arange(-len(b_norm) + 1, len(a_norm))

        peak_idx = int(np.argmax(np.abs(corr)))
        lag_samples = lags[peak_idx]
        offset_seconds = -lag_samples / sr  # sign convention: positive => b lags a

        # crude confidence: peak vs mean absolute correlation
        confidence = float(np.abs(corr[peak_idx]) / (np.mean(np.abs(corr)) + 1e-9))
        confidence = min(confidence / 20.0, 1.0)  # rough normalization to ~0-1

        return SyncResult(offset_seconds=float(offset_seconds), confidence=confidence, sample_rate=sr)

    @staticmethod
    def _normalize(x: np.ndarray) -> np.ndarray:
        x = x - np.mean(x)
        std = np.std(x)
        return x / std if std > 1e-9 else x

    @staticmethod
    def _bounded_correlate(a: np.ndarray, b: np.ndarray, max_lag: int) -> np.ndarray:
        """Cross-correlation restricted to +/- max_lag samples (faster & avoids spurious far-off peaks)."""
        n = len(a) + len(b)
        full = correlate(a, b, mode="full", method="fft")
        center = len(b) - 1
        lo = max(0, center - max_lag)
        hi = min(len(full), center + max_lag + 1)
        return full[lo:hi]

    # ------------------------------------------------------------------
    # Drift detection (offset that changes over time, e.g. clock skew)
    # ------------------------------------------------------------------

    def detect_drift(
        self,
        source_a: Union[str, "np.ndarray"],
        source_b: Union[str, "np.ndarray"],
        window_seconds: float = 5.0,
        step_seconds: float = 10.0,
        max_offset_seconds: float = 2.0,
    ) -> DriftResult:
        """
        Measure offset in successive windows across the recording to detect
        gradual drift (e.g. two devices with slightly different clock rates).
        Fits a linear model: offset(t) = drift_rate * t + intercept.
        """
        a_audio, sr_a = self._extract_audio_array(source_a)
        b_audio, sr_b = self._extract_audio_array(source_b)
        a_audio, b_audio, sr = self._resample_to_common_rate(a_audio, sr_a, b_audio, sr_b)

        window = int(window_seconds * sr)
        step = int(step_seconds * sr)
        max_lag = int(max_offset_seconds * sr)

        offsets = []
        t = 0
        while t + window < min(len(a_audio), len(b_audio)):
            a_win = self._normalize(a_audio[t : t + window])
            b_win = self._normalize(b_audio[t : t + window])
            corr = self._bounded_correlate(a_win, b_win, max_lag)
            lags = np.arange(-max_lag, max_lag + 1)[: len(corr)]
            peak_idx = int(np.argmax(np.abs(corr)))
            lag_samples = lags[peak_idx]
            offset_s = -lag_samples / sr
            offsets.append((t / sr, offset_s))
            t += step

        if len(offsets) < 2:
            return DriftResult(offsets=offsets, drift_rate=0.0, intercept=offsets[0][1] if offsets else 0.0)

        times = np.array([o[0] for o in offsets])
        vals = np.array([o[1] for o in offsets])
        slope, intercept = np.polyfit(times, vals, 1)

        return DriftResult(offsets=offsets, drift_rate=float(slope), intercept=float(intercept))

    # ------------------------------------------------------------------
    # Applying corrections
    # ------------------------------------------------------------------

    def apply_sync(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        offset: Optional[float] = None,
        replace_audio: bool = True,
    ) -> str:
        """
        Align an external audio track to a video and mux them together.

        If `offset` is None, it will be auto-detected.
        offset > 0 means the audio should be delayed (starts later) to match video.
        offset < 0 means the audio should be advanced (trimmed from the start).
        """
        if offset is None:
            offset = self.detect_offset(video_path, audio_path)

        video = VideoFileClip(video_path)
        audio = AudioFileClip(audio_path)

        if offset > 0:
            # delay audio: pad with silence at the start
            audio = audio.set_start(offset)
        elif offset < 0:
            # advance audio: trim the start
            audio = audio.subclip(-offset)

        if replace_audio:
            final_audio = audio.set_duration(video.duration)
            final = video.set_audio(final_audio)
        else:
            combined = CompositeAudioClip([video.audio, audio])
            final = video.set_audio(combined)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        final.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)

        video.close()
        audio.close()
        return output_path

    def correct_linear_drift(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        drift_result: DriftResult,
    ) -> str:
        """
        Correct gradual clock-drift by resampling the audio track's speed
        so its effective rate matches the video, then apply the intercept
        offset as a fixed shift.
        """
        video = VideoFileClip(video_path)
        audio = AudioFileClip(audio_path)

        # speed factor: if drift_rate is positive, audio is progressively
        # lagging further behind over time -> audio is running slightly slow
        # relative to video, so speed it up by (1 + drift_rate).
        speed_factor = 1.0 + drift_result.drift_rate
        audio = audio.fx(lambda c: c.speedx(speed_factor))

        if drift_result.intercept > 0:
            audio = audio.set_start(drift_result.intercept)
        elif drift_result.intercept < 0:
            audio = audio.subclip(-drift_result.intercept)

        final = video.set_audio(audio.set_duration(video.duration))
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        final.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)

        video.close()
        audio.close()
        return output_path

    # ------------------------------------------------------------------
    # Transient detection (helps find manual sync points, e.g. a clapperboard)
    # ------------------------------------------------------------------

    def find_transients(
        self,
        source: Union[str, "np.ndarray"],
        threshold_db: float = -20.0,
        min_gap_seconds: float = 0.5,
    ) -> List[float]:
        """
        Find sharp amplitude transients (e.g. claps, snaps) in an audio
        source. Returns a list of timestamps in seconds.
        """
        audio, sr = self._extract_audio_array(source)
        envelope = np.abs(audio)

        # smooth envelope slightly to avoid catching single-sample noise
        kernel_size = max(1, int(0.002 * sr))
        kernel = np.ones(kernel_size) / kernel_size
        envelope = np.convolve(envelope, kernel, mode="same")

        peak = np.max(envelope) + 1e-9
        threshold_linear = peak * (10 ** (threshold_db / 20))

        above = envelope > threshold_linear
        min_gap_samples = int(min_gap_seconds * sr)

        transients = []
        last_idx = -min_gap_samples
        i = 0
        n = len(above)
        while i < n:
            if above[i] and (i - last_idx) >= min_gap_samples:
                transients.append(i / sr)
                last_idx = i
                i += min_gap_samples
            else:
                i += 1

        return transients


# --------------------------------------------------------------------------
# Demo / CLI usage
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Detect and correct audio/video sync offset.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_p = subparsers.add_parser("detect", help="Detect offset between two audio/video sources")
    detect_p.add_argument("source_a")
    detect_p.add_argument("source_b")
    detect_p.add_argument("--max-offset", type=float, default=None)

    sync_p = subparsers.add_parser("sync", help="Apply sync correction and mux audio into video")
    sync_p.add_argument("video")
    sync_p.add_argument("audio")
    sync_p.add_argument("output")
    sync_p.add_argument("--offset", type=float, default=None, help="Manual offset override (seconds)")

    drift_p = subparsers.add_parser("drift", help="Detect gradual clock drift between two sources")
    drift_p.add_argument("source_a")
    drift_p.add_argument("source_b")

    args = parser.parse_args()
    avs = AudioVisualSync()

    if args.command == "detect":
        result = avs.detect_offset_detailed(args.source_a, args.source_b, args.max_offset)
        print(f"Offset: {result.offset_seconds:+.3f}s  (confidence ~{result.confidence:.2f}, sr={result.sample_rate})")

    elif args.command == "sync":
        out = avs.apply_sync(args.video, args.audio, args.output, offset=args.offset)
        print(f"Wrote synced file: {out}")

    elif args.command == "drift":
        result = avs.detect_drift(args.source_a, args.source_b)
        print(f"Drift rate: {result.drift_rate:+.6f} s/s, intercept: {result.intercept:+.3f}s")
        for t, off in result.offsets:
            print(f"  t={t:6.1f}s  offset={off:+.3f}s")
