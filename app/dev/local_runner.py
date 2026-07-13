import argparse

from app.core.task.dispatcher import dispatch_context
from app.dev.template_loader import load_message_template
from app.queue.message import build_task_context


def run_local_message(message_path):
    """使用本地消息模板直接调试业务代码。"""
    message = load_message_template(message_path)
    context = build_task_context(
        message,
        runtime_mode="local",
        enable_notify=False,
        enable_result_publish=False,
        enable_record=True,
    )
    return dispatch_context(context)


def main():
    parser = argparse.ArgumentParser(description="本地调试 RPA 业务")
    parser.add_argument("--message", required=True, help="本地消息模板路径")
    args = parser.parse_args()
    run_local_message(args.message)


if __name__ == "__main__":
    main()
