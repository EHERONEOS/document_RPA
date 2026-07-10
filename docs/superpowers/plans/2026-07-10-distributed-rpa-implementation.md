# 分布式 RPA 实施计划

> **给执行代理：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务执行本计划。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 构建分布式 RPA 系统的首个可用 Python 骨架，包含本地模板调试、显式船司/客户路由、任务生命周期控制和队列模式入口。

**架构：** 代码实现、设计文档、计划文档和消息模板都位于 `/Users/wangchao/weisi_code/document_RPA`。首期实现把真实 WHL 页面自动化保留为业务方法入口，同时保证路由、上下文解析、生命周期开关和本地调试行为都能在不依赖 RabbitMQ 和真实浏览器的情况下测试。

**技术栈：** Python 3.12.12、uv 风格项目元数据、标准库 `unittest`、可选 funboost/RabbitMQ 入口、可选 DrissionPage 浏览器运行时。

---

## 当前工作区说明

- `/Users/wangchao/weisi_code/document_RPA` 是本项目根目录，保存代码、测试、设计文档和 `mssage_list/msg_demo.json`。
- `/Users/wangchao/weisi_code/wise_rpa` 仅作为本次迁移前的临时代码来源，不再作为后续目标目录。
- `ZIM/` 下的历史试验代码未迁入本项目，本次首期 RPA 骨架实现不依赖它。
- `document_RPA` 已是 git 仓库；如后续需要提交，再按用户指示处理。

## 文件结构

下面所有代码路径都相对于 `/Users/wangchao/weisi_code/document_RPA`。

创建或修改：

- 修改 `.python-version`：设置项目 Python 版本为 `3.12.12`。
- 创建 `pyproject.toml`：项目元数据和依赖。
- 创建 `.env.example`：记录本地环境默认配置。
- 创建 `app/__init__.py`：应用包标记。
- 创建 `app/main.py`：队列工作进程入口。
- 创建 `app/dev/__init__.py`：本地开发包标记。
- 创建 `app/dev/template_loader.py`：本地 JSON 模板加载。
- 创建 `app/dev/local_runner.py`：本地业务调试入口。
- 创建 `app/config/__init__.py`：配置包标记。
- 创建 `app/config/settings.py`：从环境变量读取类型化配置。
- 创建 `app/config/queue_config.py`：队列列表解析。
- 创建 `app/core/task/__init__.py`：任务包标记。
- 创建 `app/core/task/context.py`：`TaskContext` 和队列名解析。
- 创建 `app/core/task/result.py`：任务结果载荷模型。
- 创建 `app/core/task/errors.py`：共享异常类。
- 创建 `app/core/task/dispatcher.py`：船司路由加载。
- 创建 `app/core/task/base_task.py`：RPA 任务生命周期。
- 创建 `app/core/browser/__init__.py`：浏览器包标记。
- 创建 `app/core/browser/port.py`：按用户和船司维护固定端口映射。
- 创建 `app/core/browser/options.py`：浏览器选项数据。
- 创建 `app/core/browser/manager.py`：DrissionPage 浏览器管理器。
- 创建 `app/core/page/__init__.py`：页面辅助包标记。
- 创建 `app/core/page/dom.py`：DOM 辅助方法。
- 创建 `app/core/page/wait.py`：页面等待辅助方法。
- 创建 `app/core/integrations/__init__.py`：外部集成包标记。
- 创建 `app/core/integrations/notifier.py`：处理中通知客户端。
- 创建 `app/core/integrations/publisher.py`：结果回传客户端。
- 创建 `app/core/integrations/oss.py`：截图上传或本地路径客户端。
- 创建 `app/core/integrations/recorder.py`：录屏控制器。
- 创建 `app/core/integrations/captcha.py`：验证码接口。
- 创建 `app/core/logging/__init__.py`：日志包标记。
- 创建 `app/core/logging/logger.py`：中文控制台日志。
- 创建 `app/queue/__init__.py`：队列包标记。
- 创建 `app/queue/message.py`：原始 MQ 消息转换。
- 创建 `app/queue/consumer.py`：funboost 消费者注册。
- 创建 `app/queue/publisher.py`：结果回传兼容封装。
- 创建 `app/Spider/__init__.py`：船司任务包标记。
- 创建 `app/Spider/WHL/__init__.py`：WHL 包标记。
- 创建 `app/Spider/WHL/base.py`：WHL 通用任务基类。
- 创建 `app/Spider/WHL/WHL_SI.py`：WHL 通用 SI 流程。
- 创建 `app/Spider/WHL/WHL_VGM.py`：WHL 通用 VGM 流程。
- 创建 `app/Spider/WHL/FL_WHL.py`：FL 客户入口和覆盖。
- 创建 `app/Spider/WHL/router.py`：WHL 显式队列路由表。
- 创建 `tests/test_settings.py`：配置测试。
- 创建 `tests/test_message_context.py`：消息解析测试。
- 创建 `tests/test_routing.py`：路由和分发器测试。
- 创建 `tests/test_base_task_lifecycle.py`：生命周期开关测试。
- 创建 `tests/test_browser_and_dom.py`：浏览器固定端口和 DOM 辅助方法测试。
- 创建 `tests/test_local_runner.py`：本地模板运行器测试。

---

### 任务 1：项目元数据和配置

**文件：**
- 修改：`.python-version`
- 创建：`pyproject.toml`
- 创建：`.env.example`
- 创建：`app/__init__.py`
- 创建：`app/config/__init__.py`
- 创建：`app/config/settings.py`
- 创建：`app/config/queue_config.py`
- 测试：`tests/test_settings.py`

- [ ] **步骤 1：编写失败的配置测试**

创建 `tests/test_settings.py`：

```python
import os
import unittest
from unittest.mock import patch

from app.config.queue_config import parse_queue_names
from app.config.settings import Settings, str_to_bool


class SettingsTest(unittest.TestCase):
    def test_str_to_bool_accepts_common_true_values(self):
        self.assertTrue(str_to_bool("true"))
        self.assertTrue(str_to_bool("1"))
        self.assertTrue(str_to_bool("YES"))
        self.assertFalse(str_to_bool("false"))
        self.assertFalse(str_to_bool(""))

    def test_parse_queue_names_trims_empty_values(self):
        self.assertEqual(parse_queue_names(" FL_WHL_SI, ,FL_WHL_VGM "), ["FL_WHL_SI", "FL_WHL_VGM"])

    def test_settings_reads_environment(self):
        env = {
            "APP_ENV": "local",
            "RPA_QUEUES": "FL_WHL_SI",
            "RABBITMQ_HOST": "192.168.60.106",
            "RABBITMQ_PORT": "5672",
            "RABBITMQ_USER": "guest",
            "RABBITMQ_PASSWORD": "guest",
            "BROWSER_PORT_START": "9000",
            "BROWSER_PORT_END": "9200",
            "DOWNLOAD_DIR": "runtime/downloads",
            "BROWSER_USER_DATA_DIR": "runtime/browser_profiles",
            "ENABLE_RECORD": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.app_env, "local")
        self.assertEqual(settings.rpa_queues, ["FL_WHL_SI"])
        self.assertEqual(settings.rabbitmq_host, "192.168.60.106")
        self.assertEqual(settings.rabbitmq_port, 5672)
        self.assertFalse(settings.enable_record)
        self.assertEqual(settings.browser_port_start, 9000)
        self.assertEqual(settings.browser_port_end, 9200)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行配置测试并确认失败**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_settings -v
```

预期：FAIL，错误为无法导入 `app.config`。

- [ ] **步骤 3：添加项目元数据和配置实现**

修改 `.python-version`：

```text
3.12.12
```

创建 `pyproject.toml`：

```toml
[project]
name = "wise-rpa"
version = "0.1.0"
description = "Distributed RPA workers for carrier document automation"
requires-python = "==3.12.12"
dependencies = [
    "DrissionPage",
    "funboost",
    "python-dotenv",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

创建 `.env.example`：

```dotenv
APP_ENV=local
RPA_QUEUES=FL_WHL_SI
RABBITMQ_HOST=192.168.60.106
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
BROWSER_PORT_START=9000
BROWSER_PORT_END=9200
DOWNLOAD_DIR=runtime/downloads
BROWSER_USER_DATA_DIR=runtime/browser_profiles
ENABLE_RECORD=false
```

创建 `app/__init__.py`：

```python
"""Wise RPA application package."""
```

创建 `app/config/__init__.py`：

```python
"""Configuration helpers."""
```

创建 `app/config/queue_config.py`：

```python
def parse_queue_names(raw_value: str) -> list[str]:
    """解析需要消费的队列名列表。"""
    return [item.strip().upper() for item in raw_value.split(",") if item.strip()]
```

创建 `app/config/settings.py`：

```python
import os
from dataclasses import dataclass

from app.config.queue_config import parse_queue_names


def str_to_bool(value: str | None) -> bool:
    """将环境变量字符串转换为布尔值。"""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    """应用运行配置。"""

    app_env: str
    rpa_queues: list[str]
    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_user: str
    rabbitmq_password: str
    browser_port_start: int
    browser_port_end: int
    download_dir: str
    browser_user_data_dir: str
    enable_record: bool

    @classmethod
    def from_env(cls) -> "Settings":
        """从环境变量读取配置。"""
        return cls(
            app_env=os.getenv("APP_ENV", "local"),
            rpa_queues=parse_queue_names(os.getenv("RPA_QUEUES", "FL_WHL_SI")),
            rabbitmq_host=os.getenv("RABBITMQ_HOST", "192.168.60.106"),
            rabbitmq_port=int(os.getenv("RABBITMQ_PORT", "5672")),
            rabbitmq_user=os.getenv("RABBITMQ_USER", "guest"),
            rabbitmq_password=os.getenv("RABBITMQ_PASSWORD", "guest"),
            browser_port_start=int(os.getenv("BROWSER_PORT_START", "9000")),
            browser_port_end=int(os.getenv("BROWSER_PORT_END", "9200")),
            download_dir=os.getenv("DOWNLOAD_DIR", "runtime/downloads"),
            browser_user_data_dir=os.getenv("BROWSER_USER_DATA_DIR", "runtime/browser_profiles"),
            enable_record=str_to_bool(os.getenv("ENABLE_RECORD", "false")),
        )
```

- [ ] **步骤 4：运行配置测试并确认通过**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_settings -v
```

预期：`tests.test_settings` 中所有测试 PASS。

- [ ] **步骤 5：仓库初始化后提交**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
git status
```

当前工作区已是 git 仓库；如需要提交，再按用户指示运行：

```bash
git add .python-version pyproject.toml .env.example app/__init__.py app/config tests/test_settings.py
git commit -m "chore: add rpa project settings"
```

---

### 任务 2：消息解析和任务上下文

**文件：**
- 创建：`app/core/task/__init__.py`
- 创建：`app/core/task/errors.py`
- 创建：`app/core/task/context.py`
- 创建：`app/core/task/result.py`
- 创建：`app/queue/__init__.py`
- 创建：`app/queue/message.py`
- 测试：`tests/test_message_context.py`

- [ ] **步骤 1：编写失败的消息上下文测试**

创建 `tests/test_message_context.py`：

```python
import copy
import json
import unittest
from pathlib import Path

from app.core.task.context import TaskContext, parse_queue_name
from app.core.task.errors import MessageParseError, QueueNameError
from app.queue.message import build_task_context


MESSAGE_TEMPLATE = Path("/Users/wangchao/weisi_code/document_RPA/mssage_list/msg_demo.json")


class MessageContextTest(unittest.TestCase):
    def test_parse_queue_name(self):
        customer, carrier, business = parse_queue_name("FL_WHL_SI")

        self.assertEqual(customer, "FL")
        self.assertEqual(carrier, "WHL")
        self.assertEqual(business, "SI")

    def test_parse_queue_name_rejects_invalid_value(self):
        with self.assertRaises(QueueNameError):
            parse_queue_name("FL_WHL")

    def test_build_task_context_from_template(self):
        message = json.loads(MESSAGE_TEMPLATE.read_text(encoding="utf-8"))

        context = build_task_context(message)

        self.assertIsInstance(context, TaskContext)
        self.assertEqual(context.queue_name, "FL_WHL_SI")
        self.assertEqual(context.customer_code, "FL")
        self.assertEqual(context.carrier_code, "WHL")
        self.assertEqual(context.business_code, "SI")
        self.assertEqual(context.rpa_message_id, "2054390608361074688")
        self.assertEqual(context.website_info["websiteAccount"], "WHL_DEMO_ACCOUNT")
        self.assertEqual(context.content["bookingNo"], "WZ790V50175")
        self.assertEqual(context.runtime_mode, "queue")
        self.assertTrue(context.enable_notify)
        self.assertTrue(context.enable_result_publish)

    def test_remain_content_is_deep_copy(self):
        message = json.loads(MESSAGE_TEMPLATE.read_text(encoding="utf-8"))

        context = build_task_context(message)
        context.remain_content["totalContainers"][0]["declareLiBatteries"] = "changed"

        self.assertNotEqual(context.content["totalContainers"][0]["declareLiBatteries"], "changed")

    def test_build_task_context_requires_task(self):
        with self.assertRaises(MessageParseError):
            build_task_context({"bad": copy.deepcopy({"value": 1})})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行消息上下文测试并确认失败**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_message_context -v
```

预期：FAIL，错误为无法导入 `app.core.task`。

- [ ] **步骤 3：添加任务上下文、结果、异常和消息解析**

创建 `app/core/task/__init__.py`：

```python
"""Task lifecycle models and helpers."""
```

创建 `app/core/task/errors.py`：

```python
class RpaError(Exception):
    """RPA 基础异常。"""


class MessageParseError(RpaError):
    """消息结构不正确。"""


class QueueNameError(RpaError):
    """队列名不符合客户_船司_业务格式。"""


class RouteNotFoundError(RpaError):
    """未找到队列入口路由。"""


class BrowserStartError(RpaError):
    """浏览器启动失败。"""


class LoginError(RpaError):
    """登录失败。"""


class ElementNotFoundError(RpaError):
    """页面元素不存在。"""


class BusinessError(RpaError):
    """业务填单失败。"""


class UnfilledFieldError(RpaError):
    """存在未处理字段。"""
```

创建 `app/core/task/context.py`：

```python
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from app.core.task.errors import QueueNameError


@dataclass
class TaskContext:
    """单条 RPA 消息的运行上下文。"""

    raw_message: dict[str, Any]
    task: dict[str, Any]
    queue_name: str
    rpa_message_id: str
    customer_code: str
    carrier_code: str
    business_code: str
    website_info: dict[str, Any]
    content: dict[str, Any]
    remain_content: dict[str, Any]
    runtime_mode: str = "queue"
    enable_notify: bool = True
    enable_result_publish: bool = True
    enable_record: bool | None = None


def parse_queue_name(queue_name: str) -> tuple[str, str, str]:
    """解析客户_船司_业务格式的队列名。"""
    parts = [part.strip().upper() for part in queue_name.split("_") if part.strip()]
    if len(parts) != 3:
        raise QueueNameError(f"队列名格式错误：{queue_name}")
    return parts[0], parts[1], parts[2]


def copy_content(content: dict[str, Any]) -> dict[str, Any]:
    """深拷贝填单内容，用于追踪未填字段。"""
    return copy.deepcopy(content)
```

创建 `app/core/task/result.py`：

```python
from dataclasses import dataclass, field


@dataclass
class TaskResult:
    """任务回传结果。"""

    rpa_message_id: str
    queue_name: str
    success: bool
    message: str
    error_type: str = ""
    unfilled_fields: list[str] = field(default_factory=list)
    screenshot_url: str = ""
    record_url: str = ""

    def to_payload(self) -> dict[str, object]:
        """转换为结果回传 payload。"""
        return {
            "rpaMessageId": self.rpa_message_id,
            "queueName": self.queue_name,
            "success": self.success,
            "message": self.message,
            "errorType": self.error_type,
            "unfilledFields": self.unfilled_fields,
            "screenshotUrl": self.screenshot_url,
            "recordUrl": self.record_url,
        }
```

创建 `app/queue/__init__.py`：

```python
"""Queue integration package."""
```

创建 `app/queue/message.py`：

```python
from __future__ import annotations

from typing import Any

from app.core.task.context import TaskContext, copy_content, parse_queue_name
from app.core.task.errors import MessageParseError


def _require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MessageParseError(f"{name} 必须是对象")
    return value


def build_task_context(
    raw_message: dict[str, Any],
    *,
    runtime_mode: str = "queue",
    enable_notify: bool = True,
    enable_result_publish: bool = True,
    enable_record: bool | None = None,
) -> TaskContext:
    """从原始队列消息构建任务上下文。"""
    task = _require_dict(raw_message.get("task"), "task")
    queue_name = str(task.get("rpaTaskTopic") or "").strip().upper()
    if not queue_name:
        raise MessageParseError("task.rpaTaskTopic 不能为空")

    customer_code, carrier_code, business_code = parse_queue_name(queue_name)
    website_info = _require_dict(task.get("websiteInfo"), "task.websiteInfo")
    content = _require_dict(task.get("content"), "task.content")
    rpa_message_id = str(task.get("rpaMessageId") or "").strip()
    if not rpa_message_id:
        raise MessageParseError("task.rpaMessageId 不能为空")

    return TaskContext(
        raw_message=raw_message,
        task=task,
        queue_name=queue_name,
        rpa_message_id=rpa_message_id,
        customer_code=customer_code,
        carrier_code=carrier_code,
        business_code=business_code,
        website_info=website_info,
        content=content,
        remain_content=copy_content(content),
        runtime_mode=runtime_mode,
        enable_notify=enable_notify,
        enable_result_publish=enable_result_publish,
        enable_record=enable_record,
    )
```

- [ ] **步骤 4：运行消息上下文测试并确认通过**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_message_context -v
```

预期：`tests.test_message_context` 中所有测试 PASS。

- [ ] **步骤 5：仓库初始化后提交**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
git status
```

当前工作区已是 git 仓库；如需要提交，再按用户指示运行：

```bash
git add app/core/task app/queue tests/test_message_context.py
git commit -m "feat: parse rpa task messages"
```

---

### 任务 3：船司分发和 WHL 显式路由

**文件：**
- 创建：`app/core/task/base_task.py`
- 创建：`app/core/task/dispatcher.py`
- 创建：`app/Spider/__init__.py`
- 创建：`app/Spider/WHL/__init__.py`
- 创建：`app/Spider/WHL/base.py`
- 创建：`app/Spider/WHL/WHL_SI.py`
- 创建：`app/Spider/WHL/WHL_VGM.py`
- 创建：`app/Spider/WHL/FL_WHL.py`
- 创建：`app/Spider/WHL/router.py`
- 测试：`tests/test_routing.py`

- [ ] **步骤 1：编写失败的路由测试**

创建 `tests/test_routing.py`：

```python
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.task.dispatcher import dispatch_context
from app.queue.message import build_task_context
from app.Spider.WHL import router
from app.Spider.WHL.FL_WHL import FlWhlSiTask, fl_whl_si
from app.Spider.WHL.WHL_SI import WhlSiTask


MESSAGE_TEMPLATE = Path("/Users/wangchao/weisi_code/document_RPA/mssage_list/msg_demo.json")


class RoutingTest(unittest.TestCase):
    def _context(self):
        message = json.loads(MESSAGE_TEMPLATE.read_text(encoding="utf-8"))
        return build_task_context(
            message,
            runtime_mode="local",
            enable_notify=False,
            enable_result_publish=False,
            enable_record=False,
        )

    def test_whl_router_maps_full_queue_name_to_entry_function(self):
        self.assertIs(router.ROUTES["FL_WHL_SI"], fl_whl_si)

    def test_customer_task_inherits_whl_common_si(self):
        self.assertTrue(issubclass(FlWhlSiTask, WhlSiTask))

    def test_dispatch_context_loads_carrier_router(self):
        context = self._context()
        with patch("app.Spider.WHL.FL_WHL.FlWhlSiTask.run", return_value="ok") as run:
            result = dispatch_context(context)

        self.assertEqual(result, "ok")
        run.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行路由测试并确认失败**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_routing -v
```

预期：FAIL，错误为无法导入 `app.core.task.dispatcher` 和 `app.Spider`。

- [ ] **步骤 3：添加分发器和 WHL 路由骨架**

创建 `app/core/task/base_task.py`：

```python
class BaseRpaTask:
    """RPA 任务最小基类，后续任务会扩展完整生命周期。"""

    enable_record: bool = False
    incognito: bool = False
    wait_page_load: bool = False
    fail_on_unfilled_fields: bool = False

    def __init__(self, context) -> None:
        self.context = context
        self.events: list[str] = []

    def run(self):
        """执行登录和业务流程。"""
        self.login()
        self.execute_business()
        return None

    def log(self, message: str) -> None:
        """打印任务日志。"""
        print(message)

    def login(self) -> None:
        """船司登录，由船司基类实现。"""

    def execute_business(self) -> None:
        """执行业务填单，由业务类实现。"""

    def mark_field_done(self, field_name: str) -> None:
        """字段填入成功后，从 remain_content 删除。"""
        self.context.remain_content.pop(field_name, None)
```

创建 `app/core/task/dispatcher.py`：

```python
from importlib import import_module

from app.core.task.context import TaskContext
from app.core.task.errors import RouteNotFoundError


def dispatch_context(context: TaskContext):
    """根据船司代码加载 router 并分发任务。"""
    module_name = f"app.Spider.{context.carrier_code}.router"
    try:
        router = import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RouteNotFoundError(f"未找到船司路由：{context.carrier_code}") from exc

    dispatch = getattr(router, "dispatch", None)
    if dispatch is None:
        raise RouteNotFoundError(f"船司路由缺少 dispatch 方法：{context.carrier_code}")
    return dispatch(context)
```

创建 `app/Spider/__init__.py`：

```python
"""Carrier spider package."""
```

创建 `app/Spider/WHL/__init__.py`：

```python
"""WHL carrier tasks."""
```

创建 `app/Spider/WHL/base.py`：

```python
from app.core.task.base_task import BaseRpaTask


class WhlBaseTask(BaseRpaTask):
    """WHL 船司公共能力。"""

    carrier_code = "WHL"

    def login(self) -> None:
        """执行 WHL 登录。"""
        self.log("执行 WHL 登录入口")
```

创建 `app/Spider/WHL/WHL_SI.py`：

```python
from app.Spider.WHL.base import WhlBaseTask


class WhlSiTask(WhlBaseTask):
    """WHL 通用 SI 业务流程。"""

    business_code = "SI"
    incognito = False
    wait_page_load = False

    def execute_business(self) -> None:
        """执行 WHL SI 通用填单流程。"""
        self.fill_booking_no()
        self.fill_shipper()
        self.fill_consignee()
        self.fill_goods()
        self.submit_or_save()

    def fill_booking_no(self) -> None:
        """填写订舱号。"""
        self.mark_field_done("bookingNo")

    def fill_shipper(self) -> None:
        """填写发货人。"""
        self.mark_field_done("shipperTitle")
        self.mark_field_done("shipperAddress")

    def fill_consignee(self) -> None:
        """填写收货人。"""
        self.mark_field_done("consigneeTitle")
        self.mark_field_done("consigneeAddress")

    def fill_goods(self) -> None:
        """填写货物信息。"""
        self.mark_field_done("totalGoodsDesc")
        self.mark_field_done("totalGrossWeight")

    def submit_or_save(self) -> None:
        """保存或提交。"""
        self.log("WHL SI 保存或提交入口")
```

创建 `app/Spider/WHL/WHL_VGM.py`：

```python
from app.Spider.WHL.base import WhlBaseTask


class WhlVgmTask(WhlBaseTask):
    """WHL 通用 VGM 业务流程。"""

    business_code = "VGM"
    incognito = False

    def execute_business(self) -> None:
        """执行 WHL VGM 通用填单流程。"""
        self.mark_field_done("bookingNo")
        self.log("WHL VGM 填单入口")
```

创建 `app/Spider/WHL/FL_WHL.py`：

```python
from app.Spider.WHL.WHL_SI import WhlSiTask
from app.Spider.WHL.WHL_VGM import WhlVgmTask


class FlWhlSiTask(WhlSiTask):
    """FL 客户的 WHL SI 任务。"""

    incognito = False

    def fill_shipper(self) -> None:
        """FL 客户发货人填写个性化入口。"""
        super().fill_shipper()


def fl_whl_si(context):
    """FL_WHL_SI 队列入口。"""
    return FlWhlSiTask(context).run()


def fl_whl_vgm(context):
    """FL_WHL_VGM 队列入口。"""
    return WhlVgmTask(context).run()
```

创建 `app/Spider/WHL/router.py`：

```python
from app.core.task.context import TaskContext
from app.core.task.errors import RouteNotFoundError
from app.Spider.WHL.FL_WHL import fl_whl_si, fl_whl_vgm


ROUTES = {
    "FL_WHL_SI": fl_whl_si,
    "FL_WHL_VGM": fl_whl_vgm,
}


def dispatch(context: TaskContext):
    """根据完整队列名分发到客户入口方法。"""
    route = ROUTES.get(context.queue_name.upper())
    if route is None:
        raise RouteNotFoundError(f"WHL 未配置队列入口：{context.queue_name}")
    return route(context)
```

- [ ] **步骤 4：运行路由测试并确认通过**

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_routing -v
```

预期：`tests.test_routing` 中所有测试 PASS。

- [ ] **步骤 5：仓库初始化后提交**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
git status
```

当前工作区已是 git 仓库；如需要提交，再按用户指示运行：

```bash
git add app/core/task/base_task.py app/core/task/dispatcher.py app/Spider tests/test_routing.py
git commit -m "feat: add carrier routing"
```

---

### 任务 4：任务生命周期和集成开关

**文件：**
- 修改：`app/core/task/base_task.py`
- 创建：`app/core/integrations/__init__.py`
- 创建：`app/core/integrations/notifier.py`
- 创建：`app/core/integrations/publisher.py`
- 创建：`app/core/integrations/oss.py`
- 创建：`app/core/integrations/recorder.py`
- 创建：`app/core/integrations/captcha.py`
- 创建：`app/core/logging/__init__.py`
- 创建：`app/core/logging/logger.py`
- 测试：`tests/test_base_task_lifecycle.py`

- [ ] **步骤 1：编写失败的生命周期测试**

创建 `tests/test_base_task_lifecycle.py`：

```python
import json
import unittest
from pathlib import Path

from app.core.task.base_task import BaseRpaTask
from app.queue.message import build_task_context


MESSAGE_TEMPLATE = Path("/Users/wangchao/weisi_code/document_RPA/mssage_list/msg_demo.json")


class FakeBrowserManager:
    def __init__(self):
        self.close_called = False

    def start(self, context, task):
        self.context = context
        self.task = task
        return "page"

    def close(self):
        self.close_called = True


class FakeNotifier:
    def __init__(self):
        self.calls = []

    def notify_processing(self, context):
        self.calls.append(context.queue_name)


class FakePublisher:
    def __init__(self):
        self.payloads = []

    def publish_result(self, result):
        self.payloads.append(result.to_payload())


class FakeRecorder:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self, context):
        self.started = True

    def stop(self, context):
        self.stopped = True
        return ""


class SampleTask(BaseRpaTask):
    enable_record = True

    def login(self):
        self.events.append("login")

    def execute_business(self):
        self.events.append("business")
        self.mark_field_done("bookingNo")


class BaseTaskLifecycleTest(unittest.TestCase):
    def _context(self, **overrides):
        message = json.loads(MESSAGE_TEMPLATE.read_text(encoding="utf-8"))
        values = {
            "runtime_mode": "queue",
            "enable_notify": True,
            "enable_result_publish": True,
            "enable_record": None,
        }
        values.update(overrides)
        return build_task_context(message, **values)

    def test_queue_mode_notifies_records_publishes_and_keeps_browser(self):
        context = self._context()
        browser = FakeBrowserManager()
        notifier = FakeNotifier()
        publisher = FakePublisher()
        recorder = FakeRecorder()

        task = SampleTask(
            context,
            browser_manager=browser,
            notifier=notifier,
            publisher=publisher,
            recorder=recorder,
        )
        task.run()

        self.assertEqual(task.events, ["login", "business"])
        self.assertEqual(notifier.calls, ["FL_WHL_SI"])
        self.assertTrue(recorder.started)
        self.assertTrue(recorder.stopped)
        self.assertFalse(browser.close_called)
        self.assertEqual(publisher.payloads[0]["success"], True)
        self.assertIn("bookingNo", context.content)
        self.assertNotIn("bookingNo", context.remain_content)

    def test_local_mode_skips_notify_record_and_publish(self):
        context = self._context(
            runtime_mode="local",
            enable_notify=False,
            enable_result_publish=False,
            enable_record=False,
        )
        browser = FakeBrowserManager()
        notifier = FakeNotifier()
        publisher = FakePublisher()
        recorder = FakeRecorder()

        task = SampleTask(
            context,
            browser_manager=browser,
            notifier=notifier,
            publisher=publisher,
            recorder=recorder,
        )
        task.run()

        self.assertEqual(notifier.calls, [])
        self.assertFalse(recorder.started)
        self.assertFalse(recorder.stopped)
        self.assertEqual(publisher.payloads, [])
        self.assertFalse(browser.close_called)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行生命周期测试并确认失败**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_base_task_lifecycle -v
```

预期：FAIL，因为最小版 `BaseRpaTask.run` 还不会通知、录屏或回传。

- [ ] **步骤 3：添加生命周期和外部集成实现**

创建 `app/core/logging/__init__.py`：

```python
"""Logging helpers."""
```

创建 `app/core/logging/logger.py`：

```python
from datetime import datetime


def log(message: str) -> None:
    """打印中文执行日志。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")
```

创建 `app/core/integrations/__init__.py`：

```python
"""External integration adapters."""
```

创建 `app/core/integrations/notifier.py`：

```python
from app.core.logging.logger import log


class ProcessingNotifier:
    """通知后台任务处理中。"""

    def notify_processing(self, context) -> None:
        log(f"通知处理中 rpaMessageId={context.rpa_message_id} queue={context.queue_name}")
```

创建 `app/core/integrations/publisher.py`：

```python
from app.core.logging.logger import log
from app.core.task.result import TaskResult


class ResultPublisher:
    """任务结果回传。"""

    def publish_result(self, result: TaskResult) -> None:
        log(f"任务结果回传 {result.to_payload()}")
```

创建 `app/core/integrations/oss.py`：

```python
from pathlib import Path


class OssClient:
    """截图和录屏文件地址处理。"""

    def local_screenshot_path(self, rpa_message_id: str) -> str:
        path = Path("runtime/screenshots") / f"{rpa_message_id}_error.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
```

创建 `app/core/integrations/recorder.py`：

```python
from app.core.logging.logger import log


class Recorder:
    """录屏控制器。"""

    def start(self, context) -> None:
        log(f"开始录屏 queue={context.queue_name}")

    def stop(self, context) -> str:
        log(f"停止录屏 queue={context.queue_name}")
        return ""
```

创建 `app/core/integrations/captcha.py`：

```python
class CaptchaSolver:
    """验证码识别入口。"""

    def solve(self, image_path: str) -> str:
        raise RuntimeError(f"当前未配置验证码识别服务：{image_path}")
```

创建 `app/core/task/base_task.py`：

```python
from __future__ import annotations

from app.core.integrations.notifier import ProcessingNotifier
from app.core.integrations.oss import OssClient
from app.core.integrations.publisher import ResultPublisher
from app.core.integrations.recorder import Recorder
from app.core.logging.logger import log
from app.core.task.context import TaskContext
from app.core.task.result import TaskResult


class BaseRpaTask:
    """RPA 任务生命周期基类。"""

    enable_record: bool = False
    incognito: bool = False
    wait_page_load: bool = False
    fail_on_unfilled_fields: bool = False

    def __init__(
        self,
        context: TaskContext,
        *,
        browser_manager=None,
        notifier=None,
        publisher=None,
        recorder=None,
        oss_client=None,
    ) -> None:
        self.context = context
        self.page = None
        self.events: list[str] = []
        if browser_manager is None:
            from app.core.browser.manager import BrowserManager

            self.browser_manager = BrowserManager()
        else:
            self.browser_manager = browser_manager
        self.notifier = notifier or ProcessingNotifier()
        self.publisher = publisher or ResultPublisher()
        self.recorder = recorder or Recorder()
        self.oss_client = oss_client or OssClient()

    def run(self):
        """执行完整任务生命周期。"""
        record_started = False
        record_url = ""
        try:
            if self.context.enable_notify:
                self.notifier.notify_processing(self.context)

            self.page = self.browser_manager.start(self.context, self)

            if self.should_record():
                self.recorder.start(self.context)
                record_started = True

            self.login()
            self.execute_business()
            unfilled_fields = self.check_unfilled_fields()
            if record_started:
                record_url = self.recorder.stop(self.context)
                record_started = False
            result = TaskResult(
                rpa_message_id=self.context.rpa_message_id,
                queue_name=self.context.queue_name,
                success=True,
                message="任务执行成功",
                unfilled_fields=unfilled_fields,
                record_url=record_url,
            )
            if self.context.enable_result_publish:
                self.publisher.publish_result(result)
            self.log(f"任务执行成功 queue={self.context.queue_name}")
            return result
        except Exception as exc:
            screenshot_url = self.oss_client.local_screenshot_path(self.context.rpa_message_id)
            result = TaskResult(
                rpa_message_id=self.context.rpa_message_id,
                queue_name=self.context.queue_name,
                success=False,
                message=str(exc),
                error_type=exc.__class__.__name__,
                unfilled_fields=list(self.context.remain_content.keys()),
                screenshot_url=screenshot_url,
                record_url=record_url,
            )
            if self.context.enable_result_publish:
                self.publisher.publish_result(result)
            self.log(f"任务执行失败 queue={self.context.queue_name} error={exc}")
            return result
        finally:
            if record_started:
                self.recorder.stop(self.context)
            self.log("任务结束，保留浏览器进程以便后续接管")

    def should_record(self) -> bool:
        """判断当前任务是否录屏。"""
        if self.context.enable_record is not None:
            return self.context.enable_record
        return self.enable_record

    def log(self, message: str) -> None:
        """打印任务日志。"""
        log(message)

    def login(self) -> None:
        """船司登录，由船司基类实现。"""
        raise NotImplementedError("子类必须实现 login 方法")

    def execute_business(self) -> None:
        """执行业务填单，由具体业务类实现。"""
        raise NotImplementedError("子类必须实现 execute_business 方法")

    def mark_field_done(self, field_name: str) -> None:
        """字段填入成功后，从 remain_content 删除。"""
        self.context.remain_content.pop(field_name, None)

    def check_unfilled_fields(self) -> list[str]:
        """检查未填字段。"""
        unfilled_fields = list(self.context.remain_content.keys())
        if unfilled_fields:
            self.log(f"存在未处理字段：{unfilled_fields}")
        return unfilled_fields
```

- [ ] **步骤 4：运行生命周期和路由测试**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_base_task_lifecycle tests.test_routing -v
```

预期：生命周期和路由测试全部 PASS。

- [ ] **步骤 5：仓库初始化后提交**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
git status
```

当前工作区已是 git 仓库；如需要提交，再按用户指示运行：

```bash
git add app/core/task/base_task.py app/core/integrations app/core/logging tests/test_base_task_lifecycle.py
git commit -m "feat: add task lifecycle"
```

---

### 任务 5：浏览器固定端口管理和 DOM 辅助方法

**文件：**
- 创建：`app/core/browser/__init__.py`
- 创建：`app/core/browser/port.py`
- 创建：`app/core/browser/options.py`
- 创建：`app/core/browser/manager.py`
- 创建：`app/core/page/__init__.py`
- 创建：`app/core/page/dom.py`
- 创建：`app/core/page/wait.py`
- 测试：`tests/test_browser_and_dom.py`

- [ ] **步骤 1：编写失败的浏览器固定端口和 DOM 测试**

创建 `tests/test_browser_and_dom.py`：

```python
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.core.browser.manager import BrowserManager
from app.core.browser.port import BrowserPortRegistry
from app.core.page.dom import DomHelper
from app.core.task.errors import ElementNotFoundError


class FakeElement:
    def __init__(self, text="", value=""):
        self.text = text
        self.value = value
        self.clicked = False
        self.input_value = None

    def click(self):
        self.clicked = True

    def input(self, value, clear=True):
        self.input_value = value

    def attr(self, name):
        if name == "value":
            return self.value
        return None


class FakePage:
    def __init__(self, elements):
        self.elements = elements

    def ele(self, locator, timeout=0):
        return self.elements.get(locator)


class BrowserAndDomTest(unittest.TestCase):
    def test_port_registry_reuses_same_profile_port(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = BrowserPortRegistry(Path(temp_dir) / "port_registry.json", 9000, 9002)

            first_port = registry.resolve_port("DEMO_WHL")
            second_port = registry.resolve_port("OTHER_WHL")
            reused_port = registry.resolve_port("DEMO_WHL")

        self.assertEqual(first_port, 9000)
        self.assertEqual(second_port, 9001)
        self.assertEqual(reused_port, 9000)

    def test_browser_manager_builds_stable_profile_options(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = SimpleNamespace(
                browser_port_start=9000,
                browser_port_end=9200,
                browser_user_data_dir=str(Path(temp_dir) / "profiles"),
                download_dir=str(Path(temp_dir) / "downloads"),
            )
            registry = BrowserPortRegistry(Path(temp_dir) / "port_registry.json", 9000, 9200)
            context = SimpleNamespace(
                website_info={"websiteUserName": "DEMO"},
                carrier_code="WHL",
                queue_name="FL_WHL_SI",
            )
            task = SimpleNamespace(incognito=True)
            manager = BrowserManager(settings=settings, registry=registry)

            first_options = manager.build_options(context, task)
            second_options = manager.build_options(context, task)

        self.assertEqual(first_options.port, 9000)
        self.assertEqual(second_options.port, 9000)
        self.assertTrue(first_options.user_data_path.endswith("DEMO_WHL"))
        self.assertTrue(first_options.incognito)

    def test_dom_helper_clicks_and_inputs(self):
        button = FakeElement()
        field = FakeElement(value="old")
        page = FakePage({"css:button": button, "css:input": field})
        helper = DomHelper(page)

        self.assertTrue(helper.click("css:button", "提交按钮"))
        self.assertTrue(helper.input_text("css:input", "hello", "输入框"))

        self.assertTrue(button.clicked)
        self.assertEqual(field.input_value, "hello")
        self.assertEqual(helper.get_value("css:input", "输入框"), "old")

    def test_dom_helper_required_missing_element_raises(self):
        helper = DomHelper(FakePage({}))

        with self.assertRaises(ElementNotFoundError):
            helper.click("css:missing", "缺失按钮")

    def test_dom_helper_optional_missing_element_returns_false(self):
        helper = DomHelper(FakePage({}))

        self.assertFalse(helper.click("css:missing", "缺失按钮", required=False))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行浏览器固定端口和 DOM 测试并确认失败**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_browser_and_dom -v
```

预期：FAIL，错误为无法导入 `app.core.browser` 和 `app.core.page`。

- [ ] **步骤 3：添加浏览器固定端口和 DOM 辅助方法实现**

创建 `app/core/browser/__init__.py`：

```python
"""Browser lifecycle helpers."""
```

创建 `app/core/browser/port.py`：

```python
import json
from pathlib import Path

from app.core.task.errors import BrowserStartError


class BrowserPortRegistry:
    """按浏览器标识维护固定端口映射。"""

    def __init__(self, registry_path: Path, port_start: int, port_end: int) -> None:
        self.registry_path = registry_path
        self.port_start = port_start
        self.port_end = port_end

    def resolve_port(self, profile_name: str) -> int:
        """获取浏览器标识对应的固定端口。"""
        data = self._load()
        if profile_name in data:
            return int(data[profile_name])

        used_ports = {int(port) for port in data.values()}
        for port in range(self.port_start, self.port_end + 1):
            if port not in used_ports:
                data[profile_name] = port
                self._save(data)
                return port
        raise BrowserStartError(f"未找到可分配浏览器端口：{self.port_start}-{self.port_end}")

    def _load(self) -> dict[str, int]:
        if not self.registry_path.exists():
            return {}
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, int]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

创建 `app/core/browser/options.py`：

```python
from dataclasses import dataclass, field


DEFAULT_BROWSER_ARGS = [
    "--start-maximized",
    "--ignore-certificate-errors",
]

DEFAULT_PREFS = {
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
}


@dataclass
class BrowserOptions:
    """浏览器启动参数。"""

    port: int
    user_data_path: str
    download_path: str
    incognito: bool = False
    arguments: list[str] = field(default_factory=lambda: list(DEFAULT_BROWSER_ARGS))
    prefs: dict[str, object] = field(default_factory=lambda: dict(DEFAULT_PREFS))
```

创建 `app/core/browser/manager.py`：

```python
from pathlib import Path

from app.config.settings import Settings
from app.core.browser.options import BrowserOptions
from app.core.browser.port import BrowserPortRegistry
from app.core.logging.logger import log
from app.core.task.errors import BrowserStartError


class BrowserManager:
    """DrissionPage 浏览器管理器。"""

    def __init__(self, settings: Settings | None = None, registry: BrowserPortRegistry | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.registry = registry or BrowserPortRegistry(
            Path(self.settings.browser_user_data_dir) / "port_registry.json",
            self.settings.browser_port_start,
            self.settings.browser_port_end,
        )
        self.page = None
        self.browser = None

    def build_profile_name(self, context) -> str:
        """按用户名和船司生成固定浏览器标识。"""
        username = context.website_info.get("websiteUserName") or context.website_info.get("websiteAccount") or "default"
        return f"{username}_{context.carrier_code}"

    def build_options(self, context, task) -> BrowserOptions:
        """构建浏览器启动参数。"""
        profile_name = self.build_profile_name(context)
        port = self.registry.resolve_port(profile_name)
        user_data_path = str(Path(self.settings.browser_user_data_dir) / profile_name)
        download_path = str(Path(self.settings.download_dir) / context.queue_name)
        return BrowserOptions(
            port=port,
            user_data_path=user_data_path,
            download_path=download_path,
            incognito=bool(getattr(task, "incognito", False)),
        )

    def start(self, context, task):
        """启动或接管 DrissionPage 并返回页面对象。"""
        options = self.build_options(context, task)
        Path(options.user_data_path).mkdir(parents=True, exist_ok=True)
        Path(options.download_path).mkdir(parents=True, exist_ok=True)
        try:
            from DrissionPage import ChromiumOptions, ChromiumPage

            co = ChromiumOptions()
            co.set_local_port(options.port)
            co.set_user_data_path(options.user_data_path)
            for argument in options.arguments:
                co.set_argument(argument)
            if options.incognito:
                co.set_argument("--incognito")
            co.set_pref("download.default_directory", options.download_path)
            for key, value in options.prefs.items():
                co.set_pref(key, value)
            self.page = ChromiumPage(co)
            self.browser = self.page
            log(f"浏览器启动或接管成功 port={options.port} profile={options.user_data_path}")
            return self.page
        except Exception as exc:
            raise BrowserStartError(f"浏览器启动或接管失败：{exc}") from exc

    def close(self) -> None:
        """保留浏览器进程，不主动关闭。"""
        log("任务结束后保留浏览器进程")
```

创建 `app/core/page/__init__.py`：

```python
"""Page operation helpers."""
```

创建 `app/core/page/dom.py`：

```python
from app.core.logging.logger import log
from app.core.task.errors import ElementNotFoundError


class DomHelper:
    """页面 DOM 操作封装。"""

    def __init__(self, page) -> None:
        self.page = page

    def _find(self, locator: str, name: str, required: bool):
        element = self.page.ele(locator, timeout=0)
        if element is None and required:
            raise ElementNotFoundError(f"{name}元素不存在：{locator}")
        return element

    def click(self, locator: str, name: str, required: bool = True) -> bool:
        """点击元素。"""
        element = self._find(locator, name, required)
        if element is None:
            return False
        element.click()
        log(f"点击{name}")
        return True

    def input_text(self, locator: str, value: str, name: str, required: bool = True) -> bool:
        """输入文本。"""
        element = self._find(locator, name, required)
        if element is None:
            return False
        element.input(value, clear=True)
        log(f"输入{name}")
        return True

    def get_text(self, locator: str, name: str, required: bool = True) -> str:
        """获取元素文本。"""
        element = self._find(locator, name, required)
        if element is None:
            return ""
        return getattr(element, "text", "") or ""

    def get_value(self, locator: str, name: str, required: bool = True) -> str:
        """获取 input value。"""
        element = self._find(locator, name, required)
        if element is None:
            return ""
        value = element.attr("value")
        return "" if value is None else str(value)
```

创建 `app/core/page/wait.py`：

```python
import time


def sleep_seconds(seconds: float) -> None:
    """等待指定秒数。"""
    time.sleep(seconds)
```

- [ ] **步骤 4：运行浏览器固定端口、DOM、生命周期和路由测试**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_browser_and_dom tests.test_base_task_lifecycle tests.test_routing -v
```

预期：列出的所有测试 PASS。

- [ ] **步骤 5：仓库初始化后提交**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
git status
```

当前工作区已是 git 仓库；如需要提交，再按用户指示运行：

```bash
git add app/core/browser app/core/page tests/test_browser_and_dom.py
git commit -m "feat: add browser and page helpers"
```

---

### 任务 6：本地运行器和队列入口

**文件：**
- 创建：`app/dev/__init__.py`
- 创建：`app/dev/template_loader.py`
- 创建：`app/dev/local_runner.py`
- 创建：`app/main.py`
- 创建：`app/queue/consumer.py`
- 创建：`app/queue/publisher.py`
- 测试：`tests/test_local_runner.py`

- [ ] **步骤 1：编写失败的本地运行器测试**

创建 `tests/test_local_runner.py`：

```python
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.dev.local_runner import run_local_message
from app.dev.template_loader import load_message_template


class LocalRunnerTest(unittest.TestCase):
    def test_load_message_template_reads_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as file:
            json.dump({"task": {"rpaTaskTopic": "FL_WHL_SI"}}, file)
            path = file.name

        try:
            message = load_message_template(path)
        finally:
            Path(path).unlink()

        self.assertEqual(message["task"]["rpaTaskTopic"], "FL_WHL_SI")

    def test_run_local_message_builds_local_context_and_dispatches(self):
        message_path = "/Users/wangchao/weisi_code/document_RPA/mssage_list/msg_demo.json"

        with patch("app.dev.local_runner.dispatch_context", return_value="ok") as dispatch:
            result = run_local_message(message_path)

        self.assertEqual(result, "ok")
        context = dispatch.call_args.args[0]
        self.assertEqual(context.runtime_mode, "local")
        self.assertFalse(context.enable_notify)
        self.assertFalse(context.enable_result_publish)
        self.assertFalse(context.enable_record)
        self.assertEqual(context.queue_name, "FL_WHL_SI")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行本地运行器测试并确认失败**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_local_runner -v
```

预期：FAIL，错误为无法导入 `app.dev`。

- [ ] **步骤 3：添加本地运行器和队列入口实现**

创建 `app/dev/__init__.py`：

```python
"""Local development helpers."""
```

创建 `app/dev/template_loader.py`：

```python
import json
from pathlib import Path
from typing import Any


def load_message_template(path: str) -> dict[str, Any]:
    """读取本地消息模板。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))
```

创建 `app/dev/local_runner.py`：

```python
import argparse

from app.core.task.dispatcher import dispatch_context
from app.dev.template_loader import load_message_template
from app.queue.message import build_task_context


def run_local_message(message_path: str):
    """使用本地消息模板直接调试业务代码。"""
    message = load_message_template(message_path)
    context = build_task_context(
        message,
        runtime_mode="local",
        enable_notify=False,
        enable_result_publish=False,
        enable_record=False,
    )
    return dispatch_context(context)


def main() -> None:
    parser = argparse.ArgumentParser(description="本地调试 RPA 业务")
    parser.add_argument("--message", required=True, help="本地消息模板路径")
    args = parser.parse_args()
    run_local_message(args.message)


if __name__ == "__main__":
    main()
```

创建 `app/queue/publisher.py`：

```python
from app.core.integrations.publisher import ResultPublisher


__all__ = ["ResultPublisher"]
```

创建 `app/queue/consumer.py`：

```python
from app.core.task.dispatcher import dispatch_context
from app.queue.message import build_task_context


def handle_message(raw_message: dict):
    """处理单条队列消息。"""
    context = build_task_context(raw_message)
    return dispatch_context(context)


def start_consumers(queue_names: list[str]) -> None:
    """启动 funboost 消费者。"""
    try:
        from funboost import boost, BrokerEnum
    except Exception as exc:
        raise RuntimeError(f"funboost 未安装或不可用：{exc}") from exc

    consumers = []
    for queue_name in queue_names:
        @boost(queue_name, broker_kind=BrokerEnum.RABBITMQ_AMQPSTORM)
        def consume(message, _queue_name=queue_name):
            return handle_message(message)

        consumers.append(consume)

    for consume in consumers:
        consume.consume()
```

创建 `app/main.py`：

```python
from app.config.settings import Settings
from app.queue.consumer import start_consumers


def main() -> None:
    """队列 Worker 入口。"""
    settings = Settings.from_env()
    start_consumers(settings.rpa_queues)


if __name__ == "__main__":
    main()
```

- [ ] **步骤 4：运行本地运行器测试和完整单元测试套件**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m unittest tests.test_local_runner -v
.venv/bin/python -m unittest discover -s tests -v
```

预期：本计划创建的所有测试 PASS。现有 ZIM 测试若不依赖外部服务，也应继续 PASS。

- [ ] **步骤 5：使用消息模板进行本地调试试运行**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
.venv/bin/python -m app.dev.local_runner --message /Users/wangchao/weisi_code/document_RPA/mssage_list/msg_demo.json
```

预期：运行器构建本地 `TaskContext`，进入 `fl_whl_si`，跳过通知、录屏和回传，并打印本地日志。如果当前机器状态下 DrissionPage 无法启动，生命周期应返回失败的 `TaskResult`，只保留本地日志，不调用队列回调。

- [ ] **步骤 6：仓库初始化后提交**

运行：

```bash
cd /Users/wangchao/weisi_code/document_RPA
git status
```

当前工作区已是 git 仓库；如需要提交，再按用户指示运行：

```bash
git add app/dev app/main.py app/queue/consumer.py app/queue/publisher.py tests/test_local_runner.py
git commit -m "feat: add local runner and queue entrypoints"
```

---

## 验证命令

所有任务完成后，在 `/Users/wangchao/weisi_code/document_RPA` 下运行：

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m app.dev.local_runner --message /Users/wangchao/weisi_code/document_RPA/mssage_list/msg_demo.json
```

预期：

- 单元测试通过。
- 本地运行器读取模板，并将 `FL_WHL_SI` 路由到 `fl_whl_si`。
- 本地模式关闭处理中通知、录屏和结果回传。
- 同一用户名和船司能稳定复用同一端口、同一用户目录，并在浏览器已存在时接管。
- 开发过程中浏览器失败会作为本地任务结果返回，不调用队列回调。

## 覆盖检查

- 队列名解析：任务 2。
- 消息模板解析：任务 2。
- 不依赖 MQ 的本地调试：任务 6。
- 通知、回传、录屏开关：任务 4 和任务 6。
- 浏览器固定端口映射、浏览器接管和按任务配置无痕：任务 5。
- 核心包拆分：任务 2、任务 4 和任务 5。
- WHL 通用业务文件：任务 3。
- `FL_WHL.py` 客户入口和覆盖：任务 3。
- 显式 `fl_whl_si` 路由：任务 3。
- 队列工作进程入口：任务 6。
