from __future__ import annotations

from pathlib import Path

from app.comfyui_workflow import (
    WorkflowOverrides,
    instantiate_workflow,
    load_workflow_template,
    parse_size_token,
    workflow_to_api_prompt,
)


def test_parse_size_token() -> None:
    assert parse_size_token("832*480") == (832, 480)
    assert parse_size_token("480*832") == (480, 832)


def test_instantiate_workflow_overrides_runtime_inputs(
    comfyui_object_info,
) -> None:
    template_path = (
        Path(__file__).resolve().parents[1]
        / "workflows"
        / "wan22_i2v_a14b_lowvram_template.json"
    )
    template = load_workflow_template(template_path)
    workflow = instantiate_workflow(
        template,
        WorkflowOverrides(
            image_name="uploaded/input.png",
            prompt="a moving camera shot",
            negative_prompt="bad quality",
            width=480,
            height=832,
            length=49,
            fps=16,
            output_prefix="task-123",
            seed=123456789012345,
        ),
    )
    nodes = {int(node["id"]): node for node in workflow["nodes"]}

    assert nodes[97]["widgets_values"][0] == "uploaded/input.png"
    assert nodes[93]["widgets_values"][0] == "a moving camera shot"
    assert nodes[89]["widgets_values"][0] == "bad quality"
    assert nodes[98]["widgets_values"][:3] == [480, 832, 49]
    assert nodes[108]["widgets_values"][0] == "task-123"
    assert nodes[86]["widgets_values"][1] == 123456789012345

    prompt = workflow_to_api_prompt(workflow, comfyui_object_info)
    assert prompt["97"]["inputs"]["image"] == "uploaded/input.png"
    assert prompt["93"]["inputs"]["text"] == "a moving camera shot"
    assert prompt["89"]["inputs"]["text"] == "bad quality"
    assert prompt["98"]["inputs"]["width"] == 480
    assert prompt["98"]["inputs"]["height"] == 832
    assert prompt["98"]["inputs"]["length"] == 49
    assert prompt["108"]["inputs"]["filename_prefix"] == "task-123"
    assert prompt["86"]["inputs"]["noise_seed"] == 123456789012345
    assert prompt["86"]["inputs"]["steps"] == 20
    assert prompt["86"]["inputs"]["sampler_name"] == "euler"
    assert prompt["86"]["inputs"]["scheduler"] == "simple"
    assert prompt["85"]["inputs"]["latent_image"] == ["86", 0]
    assert prompt["85"]["inputs"]["steps"] == 20
    assert prompt["85"]["inputs"]["sampler_name"] == "euler"
    assert prompt["85"]["inputs"]["scheduler"] == "simple"
