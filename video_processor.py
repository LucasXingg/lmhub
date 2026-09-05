"""视频抽帧工具：把上传的视频片段按策略拆成若干帧，供多模态模型评测使用。

解码后端按 av (PyAV) → cv2 (OpenCV) 的顺序自动选择，两者任一可用即可。
"""

import importlib.util
import re
from dataclasses import dataclass

import numpy as np
from PIL import Image

VIDEO_EXTENSIONS = ["mp4", "mov", "avi", "mkv", "webm", "m4v"]

STRATEGY_UNIFORM = "均匀采样"
STRATEGY_INTERVAL = "固定间隔"
STRATEGY_SCENE = "场景变化检测"
STRATEGY_CUSTOM = "自定义时间点"

ALL_STRATEGIES = [
    STRATEGY_UNIFORM,
    STRATEGY_INTERVAL,
    STRATEGY_SCENE,
    STRATEGY_CUSTOM,
]

# 场景检测需要顺序解码，限制探测点数量以免长视频卡死
MAX_SCENE_SAMPLES = 400

_SIGNATURE_SIZE = 64


class VideoBackendError(RuntimeError):
    pass


@dataclass
class VideoInfo:
    duration: float = 0.0
    fps: float = 0.0
    frame_count: int = 0
    width: int = 0
    height: int = 0


@dataclass
class ExtractedFrame:
    index: int
    timestamp: float
    image: Image.Image

    @property
    def label(self) -> str:
        return format_timestamp(self.timestamp)


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    whole = int(seconds)
    ms = int(round((seconds - whole) * 1000))
    if ms >= 1000:
        whole += 1
        ms -= 1000
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}.{ms:03d}"
    return f"{minutes:02d}:{secs:02d}.{ms:03d}"


def available_backend() -> str | None:
    for name in ("av", "cv2"):
        try:
            if importlib.util.find_spec(name) is not None:
                return name
        except (ImportError, ValueError):
            continue
    return None


def _require_backend() -> str:
    backend = available_backend()
    if backend is None:
        raise VideoBackendError(
            "缺少视频解码依赖，请先安装：pip install -r requirements.txt"
        )
    return backend


# ----------------------------------------------------------------------
# 时间点计算
# ----------------------------------------------------------------------


def clamp_range(info: VideoInfo, start: float, end: float) -> tuple[float, float]:
    """把用户输入的区间收敛到可解码范围，末帧留出一帧余量避免读取失败。"""
    duration = info.duration if info.duration > 0 else max(end, 0.0)
    margin = 1.0 / info.fps if info.fps > 0 else 0.04
    upper = max(0.0, duration - margin)
    start = min(max(0.0, float(start)), upper)
    end = min(max(start, float(end)), upper)
    return start, end


def uniform_timestamps(count: int, start: float, end: float) -> list[float]:
    count = max(1, int(count))
    span = max(0.0, end - start)
    if count == 1 or span <= 0:
        return [start + span / 2]
    return [start + span * i / (count - 1) for i in range(count)]


def interval_timestamps(
    step: float, start: float, end: float, max_frames: int
) -> list[float]:
    step = max(0.01, float(step))
    times = []
    t = start
    while t <= end + 1e-6 and len(times) < max_frames:
        times.append(t)
        t += step
    return times or [start]


def parse_timestamps(text: str) -> list[float]:
    """解析 "1, 2.5, 01:03" 形式的时间点列表，支持 [时:]分:秒 写法。"""
    times = []
    for token in re.split(r"[,;\s，、]+", (text or "").strip()):
        if not token:
            continue
        value = 0.0
        try:
            for part in token.split(":"):
                value = value * 60 + float(part)
        except ValueError:
            raise ValueError(f"无法解析时间点: {token}")
        times.append(value)
    return times


# ----------------------------------------------------------------------
# 探测与抽帧
# ----------------------------------------------------------------------


def probe_video(path: str) -> VideoInfo:
    if _require_backend() == "av":
        return _probe_av(path)
    return _probe_cv2(path)


def extract_frames(path: str, timestamps, progress=None) -> list[ExtractedFrame]:
    times = sorted({round(max(0.0, float(t)), 3) for t in timestamps})
    if not times:
        return []

    frames = []
    for done, (timestamp, image) in enumerate(_iter_frames(path, times), start=1):
        frames.append(
            ExtractedFrame(index=len(frames) + 1, timestamp=timestamp, image=image)
        )
        if progress:
            progress(done / len(times))
    return frames


def detect_scene_timestamps(
    path: str,
    start: float,
    end: float,
    sample_step: float,
    threshold: float,
    max_frames: int,
    progress=None,
) -> list[float]:
    """按固定步长扫描视频，保留与上一张保留帧差异超过阈值的时间点。"""
    step = max(0.05, float(sample_step))
    span = max(0.0, end - start)
    count = int(span / step) + 1
    if count > MAX_SCENE_SAMPLES:
        count = MAX_SCENE_SAMPLES
        step = span / count if count else step
    times = [start + i * step for i in range(count)]

    picked: list[float] = []
    last_signature = None
    for done, (timestamp, image) in enumerate(_iter_frames(path, times), start=1):
        signature = _signature(image)
        if last_signature is None or _difference(signature, last_signature) >= threshold:
            picked.append(timestamp)
            last_signature = signature
        if progress:
            progress(done / len(times))
        if len(picked) >= max_frames:
            break
    return picked


def _signature(image: Image.Image) -> np.ndarray:
    small = image.convert("L").resize(
        (_SIGNATURE_SIZE, _SIGNATURE_SIZE), Image.BILINEAR
    )
    return np.asarray(small, dtype=np.float32) / 255.0


def _difference(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())


def _iter_frames(path: str, times):
    if _require_backend() == "av":
        yield from _extract_av(path, times)
    else:
        yield from _extract_cv2(path, times)


# ----------------------------------------------------------------------
# PyAV 后端
# ----------------------------------------------------------------------


def _probe_av(path: str) -> VideoInfo:
    import av

    with av.open(path) as container:
        if not container.streams.video:
            raise VideoBackendError("文件中没有视频轨道")
        stream = container.streams.video[0]
        fps = float(stream.average_rate) if stream.average_rate else 0.0
        duration = 0.0
        if stream.duration is not None and stream.time_base:
            duration = float(stream.duration * stream.time_base)
        elif container.duration:
            duration = container.duration / av.time_base
        frame_count = stream.frames or (int(duration * fps) if fps else 0)
        return VideoInfo(
            duration=duration,
            fps=fps,
            frame_count=frame_count,
            width=stream.codec_context.width,
            height=stream.codec_context.height,
        )


def _extract_av(path: str, times):
    import av

    with av.open(path) as container:
        if not container.streams.video:
            raise VideoBackendError("文件中没有视频轨道")
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        time_base = float(stream.time_base) if stream.time_base else 1 / 1000

        for target in times:
            try:
                container.seek(int(target / time_base), stream=stream, backward=True)
            except Exception:
                container.seek(0)

            picked = None
            for frame in container.decode(stream):
                picked = frame
                position = float(frame.pts * time_base) if frame.pts is not None else 0.0
                if position >= target - 1e-3:
                    break
            if picked is not None:
                yield target, picked.to_image().convert("RGB")


# ----------------------------------------------------------------------
# OpenCV 后端
# ----------------------------------------------------------------------


def _probe_cv2(path: str) -> VideoInfo:
    import cv2

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise VideoBackendError("无法打开视频文件，可能是不支持的编码格式")
    try:
        fps = _finite(cap.get(cv2.CAP_PROP_FPS))
        frame_count = int(_finite(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        width = int(_finite(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
        height = int(_finite(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
        return VideoInfo(
            duration=duration,
            fps=fps,
            frame_count=frame_count,
            width=width,
            height=height,
        )
    finally:
        cap.release()


def _extract_cv2(path: str, times):
    import cv2

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise VideoBackendError("无法打开视频文件，可能是不支持的编码格式")
    try:
        for target in times:
            cap.set(cv2.CAP_PROP_POS_MSEC, target * 1000.0)
            ok, frame = cap.read()
            if not ok:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            yield target, Image.fromarray(rgb)
    finally:
        cap.release()


def _finite(value) -> float:
    value = float(value or 0.0)
    return value if np.isfinite(value) and value > 0 else 0.0
