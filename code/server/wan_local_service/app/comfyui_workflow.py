from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class WorkflowTemplateError(RuntimeError):
    pass


LOAD_IMAGE_NODE_ID = 97
POSITIVE_PROMPT_NODE_ID = 93
NEGATIVE_PROMPT_NODE_ID = 89
WAN_IMAGE_TO_VIDEO_NODE_ID = 98
CREATE_VIDEO_NODE_ID = 94
SAVE_VIDEO_NODE_ID = 108
FIRST_SAMPLER_NODE_ID = 86

LOAD_IMAGE_WIDGET_IMAGE_INDEX = 0
POSITIVE_PROMPT_WIDGET_TEXT_INDEX = 0
NEGATIVE_PROMPT_WIDGET_TEXT_INDEX = 0
WAN_IMAGE_TO_VIDEO_WIDTH_INDEX = 0
WAN_IMAGE_TO_VIDEO_HEIGHT_INDEX = 1
WAN_IMAGE_TO_VIDEO_LENGTH_INDEX = 2
CREATE_VIDEO_FPS_INDEX = 0
SAVE_VIDEO_PREFIX_INDEX = 0
FIRST_SAMPLER_SEED_INDEX = 1


@dataclass(slots=True)
class WorkflowOverrides:
    image_name: str
    prompt: str
    negative_prompt: str
    width: int
    height: int
    length: int
    fps: int
    output_prefix: str
    seed: int


def parse_size_token(size: str) -> tuple[int, int]:
    parts = [part.strip() for part in size.split("*")]
    if len(parts) != 2:
        raise WorkflowTemplateError(f"invalid size token: {size}")
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise WorkflowTemplateError(f"invalid size token: {size}") from exc
    if width <= 0 or height <= 0:
        raise WorkflowTemplateError(f"invalid size token: {size}")
    return width, height


def load_workflow_template(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorkflowTemplateError(f"failed to read workflow template: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowTemplateError(f"workflow template is not valid JSON: {path}") from exc

    if not isinstance(payload, dict) or "nodes" not in payload or "links" not in payload:
        raise WorkflowTemplateError(f"workflow template is missing nodes/links: {path}")
    return payload


def instantiate_workflow(
    template: dict[str, Any],
    overrides: WorkflowOverrides,
) -> dict[str, Any]:
    workflow = copy.deepcopy(template)
    nodes = {int(node["id"]): node for node in workflow.get("nodes", [])}

    _set_widget_value(
        nodes,
        LOAD_IMAGE_NODE_ID,
        LOAD_IMAGE_WIDGET_IMAGE_INDEX,
        overrides.image_name,
    )
    _set_widget_value(
        nodes,
        POSITIVE_PROMPT_NODE_ID,
        POSITIVE_PROMPT_WIDGET_TEXT_INDEX,
        overrides.prompt,
    )
    _set_widget_value(
        nodes,
        NEGATIVE_PROMPT_NODE_ID,
        NEGATIVE_PROMPT_WIDGET_TEXT_INDEX,
        overrides.negative_prompt,
    )
    _set_widget_value(
        nodes,
        WAN_IMAGE_TO_VIDEO_NODE_ID,
        WAN_IMAGE_TO_VIDEO_WIDTH_INDEX,
        overrides.width,
    )
    _set_widget_value(
        nodes,
        WAN_IMAGE_TO_VIDEO_NODE_ID,
        WAN_IMAGE_TO_VIDEO_HEIGHT_INDEX,
        overrides.height,
    )
    _set_widget_value(
        nodes,
        WAN_IMAGE_TO_VIDEO_NODE_ID,
        WAN_IMAGE_TO_VIDEO_LENGTH_INDEX,
        overrides.length,
    )
    _set_widget_value(
        nodes,
        CREATE_VIDEO_NODE_ID,
        CREATE_VIDEO_FPS_INDEX,
        overrides.fps,
    )
    _set_widget_value(
        nodes,
        SAVE_VIDEO_NODE_ID,
        SAVE_VIDEO_PREFIX_INDEX,
        overrides.output_prefix,
    )
    _set_widget_value(
        nodes,
        FIRST_SAMPLER_NODE_ID,
        FIRST_SAMPLER_SEED_INDEX,
        overrides.seed,
    )

    return workflow


def workflow_to_api_prompt(
    workflow: dict[str, Any],
    object_info: dict[str, Any],
) -> dict[str, Any]:
    links = workflow.get("links", [])
    link_lookup: dict[int, tuple[str, int]] = {}
    for link in links:
        if not isinstance(link, list) or len(link) < 6:
            raise WorkflowTemplateError("workflow link definition must be a 6-item list")
        link_lookup[int(link[0])] = (str(link[1]), int(link[2]))

    prompt: dict[str, Any] = {}
    for node in workflow.get("nodes", []):
        node_id = str(node["id"])
        node_type = str(node["type"])
        node_info = object_info.get(node_type)
        if not isinstance(node_info, dict):
            raise WorkflowTemplateError(f"missing object_info for node type '{node_type}'")

        if node_type == "KSamplerAdvanced":
            prompt[node_id] = {
                "class_type": node_type,
                "inputs": _build_ksampler_advanced_inputs(node, link_lookup),
                "_meta": {
                    "title": str(node.get("title") or node_type),
                },
            }
            continue

        ordered_input_names = _ordered_input_names(node_info)
        explicit_inputs = {
            str(item["name"]): item for item in node.get("inputs", []) if isinstance(item, dict)
        }
        widget_values = list(node.get("widgets_values", []))
        widget_index = 0
        prompt_inputs: dict[str, Any] = {}

        for input_name in ordered_input_names:
            explicit = explicit_inputs.get(input_name)
            if explicit is not None and explicit.get("link") is not None:
                link_id = int(explicit["link"])
                if link_id not in link_lookup:
                    raise WorkflowTemplateError(
                        f"workflow references missing link {link_id} for node {node_id}"
                    )
                origin_id, origin_slot = link_lookup[link_id]
                prompt_inputs[input_name] = [origin_id, origin_slot]
                continue

            should_use_widget = False
            if explicit is not None:
                should_use_widget = explicit.get("widget") is not None
            else:
                should_use_widget = True

            if should_use_widget and widget_index < len(widget_values):
                prompt_inputs[input_name] = widget_values[widget_index]
                widget_index += 1

        prompt[node_id] = {
            "class_type": node_type,
            "inputs": prompt_inputs,
            "_meta": {
                "title": str(node.get("title") or node_type),
            },
        }
    return prompt


def _build_ksampler_advanced_inputs(
    node: dict[str, Any],
    link_lookup: dict[int, tuple[str, int]],
) -> dict[str, Any]:
    explicit_inputs = {
        str(item["name"]): item for item in node.get("inputs", []) if isinstance(item, dict)
    }
    widgets = list(node.get("widgets_values", []))
    if len(widgets) < 10:
        raise WorkflowTemplateError(
            f"KSamplerAdvanced node {node.get('id')} does not have the expected widget layout"
        )

    prompt_inputs: dict[str, Any] = {}
    for input_name in ("model", "positive", "negative", "latent_image"):
        explicit = explicit_inputs.get(input_name)
        if explicit is None or explicit.get("link") is None:
            raise WorkflowTemplateError(
                f"KSamplerAdvanced node {node.get('id')} is missing link input '{input_name}'"
            )
        link_id = int(explicit["link"])
        if link_id not in link_lookup:
            raise WorkflowTemplateError(
                f"workflow references missing link {link_id} for node {node.get('id')}"
            )
        origin_id, origin_slot = link_lookup[link_id]
        prompt_inputs[input_name] = [origin_id, origin_slot]

    # This template comes from an older ComfyUI canvas export where the
    # KSamplerAdvanced widgets were serialized in a fixed positional layout:
    # add_noise, noise_seed, control_after_generate, steps, cfg, sampler_name,
    # scheduler, start_at_step, end_at_step, return_with_leftover_noise.
    # Recent /object_info output dropped control_after_generate and changed
    # input_order, so we map the stable semantic positions explicitly here.
    prompt_inputs.update(
        {
            "add_noise": widgets[0],
            "noise_seed": widgets[1],
            "steps": widgets[3],
            "cfg": widgets[4],
            "sampler_name": widgets[5],
            "scheduler": widgets[6],
            "start_at_step": widgets[7],
            "end_at_step": widgets[8],
            "return_with_leftover_noise": widgets[9],
        }
    )
    return prompt_inputs


def _ordered_input_names(node_info: dict[str, Any]) -> list[str]:
    input_section = node_info.get("input") or {}
    input_order = node_info.get("input_order") or {}

    ordered: list[str] = []
    for section_name in ("required", "optional"):
        section = input_section.get(section_name) or {}
        explicit_order = input_order.get(section_name) or list(section.keys())
        for name in explicit_order:
            if name not in ordered:
                ordered.append(str(name))
    return ordered


def _set_widget_value(
    nodes: dict[int, dict[str, Any]],
    node_id: int,
    widget_index: int,
    value: Any,
) -> None:
    node = nodes.get(node_id)
    if node is None:
        raise WorkflowTemplateError(f"workflow is missing node {node_id}")
    widgets = list(node.get("widgets_values", []))
    if widget_index >= len(widgets):
        raise WorkflowTemplateError(
            f"workflow node {node_id} is missing widget index {widget_index}"
        )
    widgets[widget_index] = value
    node["widgets_values"] = widgets
