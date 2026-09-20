from __future__ import annotations

import copy
import json
import math
import secrets
from pathlib import Path
from typing import Any, Mapping, Sequence


_TEMPLATE_DIR = Path(__file__).with_name("templates")
_QWEN_TEMPLATE_BY_COUNT = {
    1: "image_qwen_1.json",
    2: "image_qwen_2.json",
    3: "image_qwen_3.json",
}
_MINIMAX_TEMPLATE = "video_minimax_h3.json"
_MIN_VIDEO_FRAMES = 5
_MAX_VIDEO_FRAMES = 362
_REFERENCE_LIMITS = {"qwen": (1, 3), "minimax": (1, 9)}


def _load_template(filename: str) -> dict[str, dict[str, Any]]:
    with (_TEMPLATE_DIR / filename).open("r", encoding="utf-8") as handle:
        template = json.load(handle)
    if not isinstance(template, dict) or not all(isinstance(key, str) and isinstance(value, dict) for key, value in template.items()):
        raise ValueError(f"invalid workflow template: {filename}")
    return copy.deepcopy(template)


def _references(values: Sequence[str], kind: str) -> list[str]:
    minimum, maximum = _REFERENCE_LIMITS[kind]
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{kind} workflow requires a sequence of reference images")
    refs = list(values)
    if not minimum <= len(refs) <= maximum:
        raise ValueError(f"{kind} workflow requires {minimum} to {maximum} reference images")
    for value in refs:
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise ValueError("reference image names must be non-empty strings")
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or ":" in normalized.split("/", 1)[0] or ".." in normalized.split("/"):
            raise ValueError("reference image names must stay inside ComfyUI input")
    return refs


def _prompt_text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("prompt must be a non-empty string")
    if len(value) > 10000:
        raise ValueError("prompt is too long")
    return value


def _seed(value: int | None) -> int:
    if value is None:
        return secrets.randbits(63)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 18446744073709551615:
        raise ValueError("seed must be an unsigned 64-bit integer")
    return value


def build_qwen_prompt(reference_images: Sequence[str], prompt: str, *, seed: int | None = None) -> dict[str, dict[str, Any]]:
    refs = _references(reference_images, "qwen")
    result = _load_template(_QWEN_TEMPLATE_BY_COUNT[len(refs)])
    result["15"]["inputs"]["prompt"] = _prompt_text(prompt)
    result["20"]["inputs"]["seed"] = _seed(seed)
    for index, image_name in enumerate(refs, start=1):
        node_id = str(index)
        result[node_id]["inputs"]["image"] = image_name
        if index > 1:
            result["15"]["inputs"][f"image{index}"] = [node_id, 0]
    return result


def validate_video_dimensions(width: int, height: int) -> tuple[int, int]:
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
    ):
        raise ValueError("video width and height must be positive integers")
    return max(32, math.floor(width / 32 + 0.5) * 32), max(32, math.floor(height / 32 + 0.5) * 32)


def validate_video_frames(frames: int) -> int:
    if (
        isinstance(frames, bool)
        or not isinstance(frames, int)
        or not _MIN_VIDEO_FRAMES <= frames <= _MAX_VIDEO_FRAMES
        or (frames - 5) % 17 != 0
    ):
        raise ValueError("video frames must follow 17n+5 within 5 to 362")
    return frames


def build_minimax_prompt(
    reference_images: Sequence[str],
    prompt: str,
    *,
    width: int = 1344,
    height: int = 768,
    frames: int = 124,
    seed: int | None = None,
) -> dict[str, dict[str, Any]]:
    refs = _references(reference_images, "minimax")
    width, height = validate_video_dimensions(width, height)
    frames = validate_video_frames(frames)
    result = _load_template(_MINIMAX_TEMPLATE)
    result["16"]["inputs"]["noise_seed"] = _seed(seed)
    video = result["19"]["inputs"]
    video.update({"prompt": _prompt_text(prompt), "width": width, "height": height, "length": frames})
    for index in range(len(refs) + 1, 10):
        result.pop(str(index), None)
    for index, image_name in enumerate(refs, start=1):
        node_id = str(index)
        result[node_id]["inputs"]["image"] = image_name
        video[f"ref_images.ref_image_{index - 1}"] = [node_id, 0]
    return result


__all__ = [
    "build_minimax_prompt",
    "build_qwen_prompt",
    "validate_video_dimensions",
    "validate_video_frames",
]
