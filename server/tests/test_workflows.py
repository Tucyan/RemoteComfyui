from __future__ import annotations

import copy

import pytest

from app.comfy.workflows import (
    build_minimax_prompt,
    build_qwen_prompt,
    validate_video_dimensions,
    validate_video_frames,
)


def _nodes(prompt: dict, class_type: str) -> dict[str, dict]:
    return {node_id: node for node_id, node in prompt.items() if node["class_type"] == class_type}


@pytest.mark.parametrize("count", [1, 2, 3])
def test_qwen_accepts_one_to_three_references_and_preserves_order(count: int):
    references = [f"task/ref-{index}.png" for index in range(count)]
    prompt = build_qwen_prompt(references, "把主体改成蓝色", seed=42)

    load_images = sorted(_nodes(prompt, "LoadImage").items())
    assert [node["inputs"]["image"] for _, node in load_images] == references
    positive = prompt["15"]["inputs"]
    assert positive["image1"] == ["23", 0]
    assert [positive[f"image{index}"][0] for index in range(2, count + 1)] == [node_id for node_id, _ in load_images[1:]]
    assert prompt["15"]["inputs"]["prompt"] == "把主体改成蓝色"
    assert prompt["20"]["inputs"]["seed"] == 42
    assert prompt["22"]["inputs"]["filename_prefix"] == "RemoteComfyUI/Qwen_Edit_2511"
    assert prompt["11"]["inputs"]["unet_name"] == "qwen_image_edit_2511_int8_convrot.safetensors"


@pytest.mark.parametrize("count", [0, 4])
def test_qwen_rejects_reference_counts_outside_one_to_three(count: int):
    with pytest.raises(ValueError, match="1.*3"):
        build_qwen_prompt([f"ref-{index}.png" for index in range(count)], "edit")


def test_workflows_reject_a_single_string_instead_of_a_reference_sequence():
    with pytest.raises(ValueError, match="reference images"):
        build_qwen_prompt("one.png", "edit")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="reference images"):
        build_minimax_prompt("one.png", "video")  # type: ignore[arg-type]


def test_qwen_prompt_is_deep_copied_and_does_not_accept_output_override():
    first = build_qwen_prompt(["first.png"], "edit")
    first["15"]["inputs"]["prompt"] = "mutated"
    second = build_qwen_prompt(["second.png"], "edit")
    assert second["15"]["inputs"]["prompt"] == "edit"
    with pytest.raises(TypeError):
        build_qwen_prompt(["first.png"], "edit", output_path="unsafe")  # type: ignore[call-arg]


@pytest.mark.parametrize("count", [1, 3, 9])
def test_minimax_accepts_one_to_nine_references_and_preserves_order(count: int):
    references = [f"task/ref-{index}.png" for index in range(count)]
    prompt = build_minimax_prompt(references, "镜头缓慢推进", width=1344, height=768, frames=124, seed=7)

    node = prompt["19"]
    assert [node["inputs"][f"ref_image_{index}"][0] for index in range(1, count + 1)] == [str(index) for index in range(1, count + 1)]
    assert [prompt[str(index)]["inputs"]["image"] for index in range(1, count + 1)] == references
    assert node["inputs"]["prompt"] == "镜头缓慢推进"
    assert node["inputs"]["width"] == 1344
    assert node["inputs"]["height"] == 768
    assert node["inputs"]["length"] == 124
    assert prompt["24"]["inputs"]["filename_prefix"] == "RemoteComfyUI/MiniMax_H3"
    assert all(f"ref_image_{index}" not in node["inputs"] for index in range(count + 1, 10))


@pytest.mark.parametrize("count", [0, 10])
def test_minimax_rejects_reference_counts_outside_one_to_nine(count: int):
    with pytest.raises(ValueError, match="1.*9"):
        build_minimax_prompt([f"ref-{index}.png" for index in range(count)], "video")


@pytest.mark.parametrize("width,height", [(640, 384), (1344, 768)])
def test_video_dimensions_accept_multiples_of_32(width: int, height: int):
    assert validate_video_dimensions(width, height) == (width, height)


@pytest.mark.parametrize("width,height", [(641, 384), (640, 385), (0, 384), (4096, 32)])
def test_video_dimensions_reject_unsafe_values(width: int, height: int):
    with pytest.raises(ValueError):
        validate_video_dimensions(width, height)


@pytest.mark.parametrize("frames", [124, 141, 175, 362])
def test_video_frames_follow_17n_plus_5_within_allowed_range(frames: int):
    assert validate_video_frames(frames) == frames


@pytest.mark.parametrize("frames", [123, 125, 363, 380])
def test_video_frames_reject_values_outside_allowed_sequence(frames: int):
    with pytest.raises(ValueError):
        validate_video_frames(frames)


def test_minimax_uses_fixed_models_and_output_settings():
    prompt = build_minimax_prompt(["ref.png"], "video")
    assert prompt["10"]["inputs"] == {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}
    assert prompt["11"]["inputs"] == {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}
    assert prompt["12"]["inputs"]["unet_name"] == "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
    assert prompt["13"]["inputs"] == {
        "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "type": "minimax",
    }
    assert prompt["14"]["inputs"]["lora_name"] == "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
    assert prompt["23"]["inputs"]["fps"] == 24
    assert prompt["24"]["inputs"]["format"] == "auto"
    assert prompt["24"]["inputs"]["codec"] == "auto"


def test_template_result_mutation_does_not_leak_between_builds():
    first = build_minimax_prompt(["first.png"], "one")
    snapshot = copy.deepcopy(first)
    first["19"]["inputs"]["prompt"] = "changed"
    second = build_minimax_prompt(["second.png"], "two")
    assert snapshot["19"]["inputs"]["prompt"] == "one"
    assert second["19"]["inputs"]["prompt"] == "two"
