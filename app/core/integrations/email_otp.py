"""通过 IMAP 读取网页登录所需的一次性验证码。"""

from __future__ import annotations

import email
import imaplib
import re
from email.message import Message

from app.core.task.errors import LoginError


def read_latest_otp(
    host: str,
    username: str,
    password: str,
    *,
    subject_marker: str,
    code_pattern: str = r"\b(\d{6})\b",
    max_messages: int = 5,
) -> str:
    """从最新的匹配邮件中读取验证码，失败时给出可读的登录错误。"""
    if not host:
        raise LoginError("邮件 OTP 缺少 IMAP 主机配置")
    if not username or not password:
        raise LoginError("邮件 OTP 缺少邮箱账号或密码")

    try:
        with imaplib.IMAP4_SSL(host) as client:
            client.login(username, password)
            client.select("INBOX")
            status, data = client.search(None, "ALL")
            if status != "OK" or not data or not data[0]:
                raise LoginError("邮件 OTP 收件箱为空")

            message_ids = data[0].split()[-max_messages:]
            for message_id in reversed(message_ids):
                status, payload = client.fetch(message_id, "(RFC822)")
                if status != "OK" or not payload:
                    continue
                raw_message = next(
                    (item[1] for item in payload if isinstance(item, tuple) and len(item) > 1),
                    None,
                )
                if not raw_message:
                    continue
                message = email.message_from_bytes(raw_message)
                subject = str(message.get("Subject") or "")
                body = _message_text(message)
                if subject_marker not in subject and subject_marker not in body:
                    continue
                matched = re.search(code_pattern, body)
                if matched:
                    return matched.group(1)
    except LoginError:
        raise
    except Exception as exc:
        raise LoginError(f"读取邮件 OTP 失败：{exc}") from exc

    raise LoginError("未找到最新邮件 OTP 验证码")


def _message_text(message: Message) -> str:
    """解码普通或 multipart 邮件正文。"""
    parts = message.walk() if message.is_multipart() else (message,)
    decoded_parts = []
    for part in parts:
        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition"):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        decoded_parts.append(payload.decode(charset, errors="replace"))
    return "\n".join(decoded_parts)
