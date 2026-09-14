"""校验刻意限制且不可执行任意代码的流程格式。"""
from __future__ import annotations

import copy
import re
from typing import Any


FLOW_SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_STEP_TYPES = {"action", "set", "if", "for_each", "checkpoint"}


class FlowValidationError(ValueError):
    """流程定义格式错误，或尝试使用未支持的能力。"""


def validate_flow_definition(definition: Any) -> dict[str, Any]:
    """校验受支持的声明式子集后，返回防御性副本。

    值可通过 ``${path.to.value}`` 引用运行时数据；流程定义不接受表达式、
    导入、回调或可执行源码。
    """
    if not isinstance(definition, dict):
        raise FlowValidationError("流程定义必须是对象")
    _reject_unknown(definition, {"schemaVersion", "flowId", "flowVersion", "name", "description", "steps", "metadata"}, "流程定义")
    if definition.get("schemaVersion") != FLOW_SCHEMA_VERSION:
        raise FlowValidationError(f"schemaVersion 必须为 {FLOW_SCHEMA_VERSION}")
    _identifier(definition.get("flowId"), "flowId")
    _identifier(definition.get("flowVersion"), "flowVersion")
    _optional_display_text(definition.get("name"), "name")
    _optional_display_text(definition.get("description"), "description")
    if not isinstance(definition.get("steps"), list) or not definition["steps"]:
        raise FlowValidationError("steps 必须是非空数组")
    if "metadata" in definition and not isinstance(definition["metadata"], dict):
        raise FlowValidationError("metadata 必须是对象")
    seen: set[str] = set()
    _validate_steps(definition["steps"], seen, "steps")
    return copy.deepcopy(definition)


def _validate_steps(steps: list[Any], seen: set[str], location: str) -> None:
    for index, step in enumerate(steps):
        path = f"{location}[{index}]"
        if not isinstance(step, dict):
            raise FlowValidationError(f"{path} 必须是对象")
        step_type = step.get("type")
        if step_type not in _STEP_TYPES:
            raise FlowValidationError(f"{path}.type 不支持：{step_type!r}")
        step_id = _identifier(step.get("stepId"), f"{path}.stepId")
        if step_id in seen:
            raise FlowValidationError(f"stepId 重复：{step_id}")
        seen.add(step_id)
        _optional_display_text(step.get("name"), f"{path}.name")
        _optional_display_text(step.get("description"), f"{path}.description")
        _validate_common(step, path)
        if step_type != "action" and "timeoutSeconds" in step:
            raise FlowValidationError(f"{path}.timeoutSeconds 目前只支持 action 步骤")
        if step_type == "action":
            _reject_unknown(step, {"type", "stepId", "name", "description", "action", "inputs", "output", "timeoutSeconds", "retry"}, path)
            _identifier(step.get("action"), f"{path}.action")
            _optional_identifier(step.get("output"), f"{path}.output")
            _optional_object(step.get("inputs", {}), f"{path}.inputs")
        elif step_type == "set":
            _reject_unknown(step, {"type", "stepId", "name", "description", "target", "value", "timeoutSeconds", "retry"}, path)
            _identifier(step.get("target"), f"{path}.target")
            if "value" not in step:
                raise FlowValidationError(f"{path}.value 不能为空")
        elif step_type == "checkpoint":
            _reject_unknown(step, {"type", "stepId", "name", "description", "checkpointId", "timeoutSeconds", "retry"}, path)
            _optional_identifier(step.get("checkpointId"), f"{path}.checkpointId")
        elif step_type == "if":
            _reject_unknown(step, {"type", "stepId", "name", "description", "condition", "then", "else", "timeoutSeconds", "retry"}, path)
            _validate_condition(step.get("condition"), f"{path}.condition")
            _nested_steps(step.get("then"), f"{path}.then", seen)
            if "else" in step:
                _nested_steps(step["else"], f"{path}.else", seen)
        else:
            _reject_unknown(step, {"type", "stepId", "name", "description", "items", "item", "index", "steps", "timeoutSeconds", "retry"}, path)
            if "items" not in step:
                raise FlowValidationError(f"{path}.items 不能为空")
            _identifier(step.get("item"), f"{path}.item")
            _optional_identifier(step.get("index"), f"{path}.index")
            _nested_steps(step.get("steps"), f"{path}.steps", seen)


def _validate_common(step: dict[str, Any], path: str) -> None:
    if "timeoutSeconds" in step:
        value = step["timeoutSeconds"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise FlowValidationError(f"{path}.timeoutSeconds 必须为正数")
    if "retry" in step:
        retry = step["retry"]
        _optional_object(retry, f"{path}.retry")
        _reject_unknown(retry, {"maxAttempts", "delaySeconds"}, f"{path}.retry")
        attempts = retry.get("maxAttempts", 1)
        delay = retry.get("delaySeconds", 0)
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
            raise FlowValidationError(f"{path}.retry.maxAttempts 必须为正整数")
        if not isinstance(delay, (int, float)) or isinstance(delay, bool) or delay < 0:
            raise FlowValidationError(f"{path}.retry.delaySeconds 必须为非负数")


def _validate_condition(condition: Any, path: str) -> None:
    _optional_object(condition, path)
    _reject_unknown(condition, {"left", "operator", "right"}, path)
    if "left" not in condition:
        raise FlowValidationError(f"{path}.left 不能为空")
    if condition.get("operator", "truthy") not in {"truthy", "equals", "not_equals", "exists", "not_exists"}:
        raise FlowValidationError(f"{path}.operator 不支持")
    if condition.get("operator") in {"equals", "not_equals"} and "right" not in condition:
        raise FlowValidationError(f"{path}.right 不能为空")


def _nested_steps(value: Any, path: str, seen: set[str]) -> None:
    if not isinstance(value, list):
        raise FlowValidationError(f"{path} 必须是数组")
    _validate_steps(value, seen, path)


def _identifier(value: Any, name: str) -> str:
    value = str(value or "")
    if not _IDENTIFIER.fullmatch(value):
        raise FlowValidationError(f"{name} 必须是以字母开头的标识符")
    return value


def _optional_identifier(value: Any, name: str) -> None:
    if value is not None:
        _identifier(value, name)


def _optional_object(value: Any, name: str) -> None:
    if not isinstance(value, dict):
        raise FlowValidationError(f"{name} 必须是对象")


def _optional_display_text(value: Any, name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise FlowValidationError(f"{name} 必须是 1 至 512 个字符的文本")


def _reject_unknown(value: dict[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise FlowValidationError(f"{name} 包含不支持字段：{', '.join(sorted(unknown))}")
