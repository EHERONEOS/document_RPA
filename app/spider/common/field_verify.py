"""页面字段取值与校验的通用能力。"""

from app.core.task.errors import BusinessError, ElementNotFoundError, FormValidationError, UnfilledFieldError

_UNSET = object()


class FieldVerificationMixin:
    """为任务提供页面字段校验能力。"""

    _FIELD_DONE = object()

    def verify_page_value(
        self,
        selector: str,
        field_path,
        selector_type: str = "value",
        page=None,
        name: str | None = None,
        *,
        expected_value=_UNSET,
        mark_done: bool = True,
        skip_if_empty: bool = False,
    ) -> None:
        """读取页面字段并校验，成功后默认标记对应消息字段已处理。

        ``page`` 未传时使用任务的底层 ``self.page``；传入 ``DomHelper``
        或 Shadow Root 包装对象时，复用其统一的元素定位能力。
        ``skip_if_empty`` 为真时，空值或缺失字段不读取页面，直接标记完成。
        """
        name = name or selector
        source = page or self.page
        if expected_value is _UNSET:
            try:
                expected_value = self.get_field_value(field_path, source=self.content)
            except KeyError as error:
                if skip_if_empty:
                    if mark_done:
                        self.mark_field_done(field_path)
                    return
                raise BusinessError(f"未找到{name}对应的期望字段：{field_path}") from error

        if skip_if_empty and self._is_empty_expected_value(expected_value):
            if mark_done:
                self.mark_field_done(field_path)
            return

        actual_value = self._read_page_value(source, selector, selector_type, name)
        comparable_expected_value = expected_value
        if selector_type in {"text", "value"}:
            comparable_expected_value = "" if expected_value is None else str(expected_value)
        elif selector_type == "checked" and not isinstance(expected_value, bool):
            raise BusinessError(f"{name}的期望值必须是布尔值：{expected_value}")

        if actual_value != comparable_expected_value:
            raise FormValidationError(
                f"{name} 验证失败，实际值：{actual_value}传入期值：{expected_value}"
            )
        if mark_done:
            self.mark_field_done(field_path)

    @staticmethod
    def _is_empty_expected_value(value) -> bool:
        """判断预期值是否为空，同时保留 ``0`` 和 ``False`` 的合法性。"""
        return value is None or (isinstance(value, str) and not value.strip())

    @staticmethod
    def _parse_field_path(field_path):
        """将字段路径标准化为键和数组下标组成的列表。"""
        if isinstance(field_path, (list, tuple)):
            path = list(field_path)
        elif isinstance(field_path, str):
            path = []
            position = 0
            while position < len(field_path):
                if field_path[position] == ".":
                    raise BusinessError(f"字段路径格式错误：{field_path}")
                if field_path[position] == "[":
                    closing = field_path.find("]", position + 1)
                    index_text = field_path[position + 1:closing]
                    if closing == -1 or not index_text.isdigit():
                        raise BusinessError(f"字段路径格式错误：{field_path}")
                    path.append(int(index_text))
                    position = closing + 1
                else:
                    closing = position
                    while closing < len(field_path) and field_path[closing] not in ".[":
                        closing += 1
                    path.append(field_path[position:closing])
                    position = closing

                if position == len(field_path):
                    break
                if field_path[position] == ".":
                    position += 1
                    if position == len(field_path):
                        raise BusinessError(f"字段路径格式错误：{field_path}")
                elif field_path[position] != "[":
                    raise BusinessError(f"字段路径格式错误：{field_path}")
        else:
            raise TypeError("field_path 必须是字符串、列表或元组")

        if not path or any(
            not isinstance(item, (str, int))
            or isinstance(item, bool)
            or (isinstance(item, str) and not item)
            or (isinstance(item, int) and item < 0)
            for item in path
        ):
            raise ValueError(f"字段路径格式错误：{field_path}")
        return path

    @staticmethod
    def _format_field_path(path):
        """将标准字段路径转为便于定位的文本。"""
        result = ""
        for item in path:
            result += f"[{item}]" if isinstance(item, int) else f".{item}" if result else item
        return result

    def get_field_value(self, field_path, source=None):
        """从对象或数组结构中读取指定路径的字段值。"""
        current = self.content if source is None else source
        path = self._parse_field_path(field_path)
        for item in path:
            if isinstance(current, dict) and item in current:
                current = current[item]
            elif isinstance(current, list) and isinstance(item, int) and 0 <= item < len(current):
                current = current[item]
            else:
                raise KeyError(self._format_field_path(path))
        return current

    def mark_field_done(self, field_path, source=None):
        """从 remain_content 标记删除字段，支持嵌套对象和数组。"""
        source = self.remain_content if source is None else source
        path = self._parse_field_path(field_path)
        current = source
        parents = []

        for item in path[:-1]:
            if isinstance(current, dict) and item in current:
                parents.append((current, item))
                current = current[item]
            elif isinstance(current, list) and isinstance(item, int) and 0 <= item < len(current):
                parents.append((current, item))
                current = current[item]
            else:
                return False

        last_item = path[-1]
        if isinstance(current, dict) and last_item in current:
            current.pop(last_item)
        elif isinstance(current, list) and isinstance(last_item, int) and 0 <= last_item < len(current):
            # 保留数组下标，避免已处理项目导致后续字段路径偏移。
            current[last_item] = self._FIELD_DONE
        else:
            return False

        self._prune_completed_path(parents)
        return True

    def _prune_completed_path(self, parents):
        """仅清理本次路径上已处理完的结构，避免影响其他数组元素。"""
        for parent, item in reversed(parents):
            child = parent[item]
            child_is_complete = (
                isinstance(child, dict) and not child
            ) or (
                isinstance(child, list) and bool(child) and all(value is self._FIELD_DONE for value in child)
            )
            if not child_is_complete:
                break
            if isinstance(parent, dict):
                parent.pop(item)
            else:
                parent[item] = self._FIELD_DONE

    def _iter_unfilled_fields(self, source, path=()):
        """递归枚举 remain_content 中尚未处理的叶子字段路径。"""
        if source is self._FIELD_DONE:
            return
        if isinstance(source, dict):
            if not source:
                if path:
                    yield self._format_field_path(path)
                return
            for key, value in source.items():
                yield from self._iter_unfilled_fields(value, (*path, key))
            return
        if isinstance(source, list):
            if not source:
                if path:
                    yield self._format_field_path(path)
                return
            for index, value in enumerate(source):
                yield from self._iter_unfilled_fields(value, (*path, index))
            return
        if path:
            yield self._format_field_path(path)

    def raise_if_unfilled_fields(self, stage="填单流程"):
        """检查嵌套 remain_content 中尚未处理的字段。"""
        ignored_fields = set(self.ignored_unfilled_fields or [])
        unfilled_fields = [
            field_name
            for field_name in self._iter_unfilled_fields(self.context.remain_content)
            if field_name.split("[", 1)[0].split(".", 1)[0] not in ignored_fields
        ]
        if unfilled_fields:
            self.logger.warn(f"存在未处理字段：{unfilled_fields}")
            raise UnfilledFieldError(f"{stage}存在漏填字段：{unfilled_fields}")
        return unfilled_fields

    @staticmethod
    def _read_page_value(source, selector: str, selector_type: str, name: str):
        if selector_type == "checked":
            finder = getattr(source, "_find", None)
            element = finder(selector, name) if finder else source.ele(selector, timeout=2)
            if not element:
                raise ElementNotFoundError(f"未找到{name}：{selector}")
            return bool(element.states.is_checked)

        readers = {
            "text": "get_text",
            "value": "get_value",
        }
        try:
            reader_name = readers[selector_type]
        except KeyError as error:
            raise BusinessError(
                f"不支持的 selector_type：{selector_type}，仅支持 text、value、checked"
            ) from error

        reader = getattr(source, reader_name, None)
        if reader:
            return reader(selector, name)

        element = source.ele(selector, timeout=2)
        if not element:
            raise ElementNotFoundError(f"未找到{name}：{selector}")
        if selector_type == "text":
            return getattr(element, "text", "") or ""

        value = element.value
        return "" if value is None else str(value)
