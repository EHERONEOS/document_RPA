"""执行已校验声明式 RPA 流程的运行引擎。"""
from __future__ import annotations

import copy
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.flow.schema import validate_flow_definition

_REFERENCE = re.compile(r"^\$\{([A-Za-z][A-Za-z0-9_.-]*)\}$")


class FlowExecutionError(RuntimeError):
    pass


class FlowActionTimeout(FlowExecutionError):
    pass


@dataclass
class FlowCheckpoint:
    checkpoint_id: str
    step_id: str
    variables: dict[str, Any]


@dataclass
class FlowExecutionResult:
    variables: dict[str, Any]
    step_log: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: list[FlowCheckpoint] = field(default_factory=list)


@dataclass
class ActionContext:
    task_context: Any
    variables: dict[str, Any]
    step_id: str


class ActionRegistry:
    """流程可调用的适配器与通用动作显式白名单。"""

    def __init__(self):
        self._actions: dict[str, Callable[[ActionContext, dict[str, Any]], Any]] = {}

    def register(self, name: str, handler: Callable[[ActionContext, dict[str, Any]], Any]) -> None:
        if name in self._actions:
            raise ValueError(f"流程动作已注册：{name}")
        if not callable(handler):
            raise TypeError("流程动作必须可调用")
        self._actions[name] = handler

    def invoke(self, name: str, context: ActionContext, inputs: dict[str, Any]) -> Any:
        try:
            return self._actions[name](context, inputs)
        except KeyError as exc:
            raise FlowExecutionError(f"未注册流程动作：{name}") from exc


class FlowRuntime:
    def __init__(self, registry: ActionRegistry | None = None, *, sleep: Callable[[float], None] = time.sleep):
        self.registry = registry or ActionRegistry()
        self.sleep = sleep

    def run(self, definition: dict[str, Any], task_context: Any) -> FlowExecutionResult:
        definition = validate_flow_definition(definition)
        variables = {
            "task": copy.deepcopy(task_context.task),
            "content": copy.deepcopy(task_context.content),
            "websiteInfo": copy.deepcopy(task_context.website_info),
            "flow": {"id": definition["flowId"], "version": definition["flowVersion"]},
        }
        result = FlowExecutionResult(variables=variables)
        self._run_steps(definition["steps"], task_context, result)
        return result

    def _run_steps(self, steps: list[dict[str, Any]], task_context: Any, result: FlowExecutionResult) -> None:
        for step in steps:
            self._run_step(step, task_context, result)

    def _run_step(self, step: dict[str, Any], task_context: Any, result: FlowExecutionResult) -> None:
        reporter = getattr(task_context, "task_event_reporter", None)
        if reporter is not None:
            reporter.step_changed(step["stepId"])
        started = time.monotonic()
        attempts = 0
        retry = step.get("retry", {})
        max_attempts = retry.get("maxAttempts", 1)
        while True:
            attempts += 1
            try:
                self._run_step_once(step, task_context, result)
                result.step_log.append({"stepId": step["stepId"], "status": "SUCCEEDED", "attempt": attempts, "durationMs": round((time.monotonic() - started) * 1000)})
                return
            except Exception as exc:
                if attempts >= max_attempts:
                    result.step_log.append({"stepId": step["stepId"], "status": "FAILED", "attempt": attempts, "durationMs": round((time.monotonic() - started) * 1000), "error": str(exc)})
                    raise FlowExecutionError(f"步骤 {step['stepId']} 执行失败：{exc}") from exc
                self.sleep(retry.get("delaySeconds", 0))

    def _run_step_once(self, step: dict[str, Any], task_context: Any, result: FlowExecutionResult) -> None:
        step_type = step["type"]
        if step_type == "set":
            _set_path(result.variables, step["target"], _resolve(step["value"], result.variables))
        elif step_type == "checkpoint":
            result.checkpoints.append(FlowCheckpoint(step.get("checkpointId") or step["stepId"], step["stepId"], copy.deepcopy(result.variables)))
        elif step_type == "if":
            branch = step["then"] if _evaluate(step["condition"], result.variables) else step.get("else", [])
            self._run_steps(branch, task_context, result)
        elif step_type == "for_each":
            items = _resolve(step["items"], result.variables)
            if not isinstance(items, list):
                raise FlowExecutionError(f"步骤 {step['stepId']} 的 items 必须解析为数组")
            for index, item in enumerate(items):
                _set_path(result.variables, step["item"], item)
                if step.get("index"):
                    _set_path(result.variables, step["index"], index)
                self._run_steps(step["steps"], task_context, result)
        else:
            inputs = _resolve(step.get("inputs", {}), result.variables)
            action_context = ActionContext(task_context, result.variables, step["stepId"])
            output = self._invoke_action(step, action_context, inputs)
            if step.get("output"):
                _set_path(result.variables, step["output"], output)

    def _invoke_action(self, step: dict[str, Any], context: ActionContext, inputs: dict[str, Any]) -> Any:
        timeout = step.get("timeoutSeconds")
        if timeout is None:
            return self.registry.invoke(step["action"], context, inputs)
        outcome: dict[str, Any] = {}
        completed = threading.Event()

        def invoke() -> None:
            try:
                outcome["value"] = self.registry.invoke(step["action"], context, inputs)
            except BaseException as exc:  # 由当前执行线程在等待后重新抛出
                outcome["error"] = exc
            finally:
                completed.set()

        threading.Thread(target=invoke, daemon=True).start()
        if not completed.wait(timeout):
            raise FlowActionTimeout(f"超过 {timeout} 秒")
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("value")


def _resolve(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        match = _REFERENCE.fullmatch(value)
        if match:
            return copy.deepcopy(_get_path(variables, match.group(1)))
        return value
    if isinstance(value, list):
        return [_resolve(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, variables) for key, item in value.items()}
    return copy.deepcopy(value)


def _evaluate(condition: dict[str, Any], variables: dict[str, Any]) -> bool:
    operator = condition.get("operator", "truthy")
    if operator == "exists":
        return _path_exists(variables, _reference_path(condition["left"]))
    if operator == "not_exists":
        return not _path_exists(variables, _reference_path(condition["left"]))
    left = _resolve(condition["left"], variables)
    if operator == "truthy":
        return bool(left)
    right = _resolve(condition["right"], variables)
    return left == right if operator == "equals" else left != right


def _reference_path(value: Any) -> str:
    match = _REFERENCE.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise FlowExecutionError("exists 条件的 left 必须是变量引用")
    return match.group(1)


def _get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise FlowExecutionError(f"变量不存在：{path}")
        current = current[part]
    return current


def _path_exists(value: Any, path: str) -> bool:
    try:
        _get_path(value, path)
    except FlowExecutionError:
        return False
    return True


def _set_path(value: dict[str, Any], path: str, item: Any) -> None:
    parts = path.split(".")
    current = value
    for part in parts[:-1]:
        next_value = current.get(part)
        if next_value is None:
            next_value = {}
            current[part] = next_value
        if not isinstance(next_value, dict):
            raise FlowExecutionError(f"无法写入变量路径：{path}")
        current = next_value
    current[parts[-1]] = copy.deepcopy(item)
