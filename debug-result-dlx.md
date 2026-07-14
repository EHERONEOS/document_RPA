# Debug Session: result-dlx
- **Status**: [OPEN]
- **Issue**: 结果回传消息发布后直接进入死信队列
- **Debug Server**: N/A
- **Log File**: N/A

## Reproduction Steps
1. 调用 `ResultPublisher.send_msg_to_queue(..., delay>0)` 发布结果回传消息。
2. 观察 RabbitMQ 中 `gcp_document_update` 主队列与对应死信队列的流转情况。
3. 当前现象是消息没有按预期延迟处理，而是直接进入死信队列。

## Hypotheses & Verification
| ID | Hypothesis | Likelihood | Effort | Evidence |
|----|------------|------------|--------|----------|
| A | 下游消费者处理这条结果消息时抛异常，达到重试上限后被 funboost 推入 `<queue>_dlx` | High | Low | Pending |
| B | 结果回传消息体结构与下游约定不一致，例如多包了一层 `task` 或字段名不匹配 | High | Low | Pending |
| C | 当前队列声明带了死信交换机参数，且现有队列属性与代码声明不一致，导致消息路由异常 | Med | Med | Pending |
| D | `countdown` 在该链路并不是 RabbitMQ 原生延迟，而是 funboost 消费端本地调度；下游并非按这种模式消费 | High | Low | Pending |
| E | 发布端使用的队列本身就是业务死信/超时转发链路的一环，导致看起来像“直接进死信” | Med | Med | Pending |

## Log Evidence
- 已确认 `funboost` 的 `countdown` 会在消费端解析后本地调度，而不是发布端直接声明 RabbitMQ 延迟队列。
- 已确认项目消费者默认 `is_push_to_dlx_queue_when_retry_max_times = True`。
- 已确认实际运行环境为项目 `.venv` 中的 `funboost 54.8`，`publish()` 接口使用 `task_options`，不再支持 `priority_control_config`。
- 已捕获 RabbitMQ 运行时错误：`PRECONDITION_FAILED - inequivalent arg 'x-dead-letter-exchange'`，说明 `gcp_document_update` 现有队列的死信交换机参数与发布端声明不一致。

## Verification Conclusion
- 已将 `ResultPublisher.send_msg_to_queue()` 切换为复用项目统一的 `build_rabbitmq_broker_config()`，并指定 `RabbitmqPublisherWithDlx` 来按现有队列参数声明发布者。
- 待验证修复后是否仍出现 `PRECONDITION_FAILED` 或进入死信队列。
