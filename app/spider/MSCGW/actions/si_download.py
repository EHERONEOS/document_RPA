"""通过已登录浏览器下载 MSC FreeForm 草稿件。

链路与 wise_reverse 的 get_attachment 一致：
查 FreeForm eSI 列表、按单号匹配，再调用 ShowFreeFormSiWithoutBlNumber
并下载 getdocument PDF。登录 Cookie、AccessToken 和用户头都取自当前浏览器，
请求也在该浏览器内发出，因此这里不处理代理。
"""

from __future__ import annotations

import base64
import json
import re
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urljoin, urlparse

from DrissionPage.errors import JavaScriptError

from app.core.task.errors import BusinessError

if TYPE_CHECKING:
    from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask


_BASE_URL = "https://www.mymsc.com"
_DASHBOARD_GRAPHQL = "https://services.mymsc.com/dashboard/graphql"
_SHOW_FREE_FORM_SI_URL = f"{_BASE_URL}/myMSC/Dashboard/ShowFreeFormSiWithoutBlNumber"
_LIST_LOOKBACK_DAYS = 60
_REQUEST_TIMEOUT = 90

_FREE_FORM_LIST_QUERY = """
    query GetFreeFormeSiList($fromDate: Date!, $toDate: Date!) {
  freeFormeSiList(fromDate: $fromDate, toDate: $toDate) {
    items {
      agencyId
      headerId
      bookingNumbers
      status
      portOfLoad
      portOfDischarge
      vessel
      voyage
      originalCreateDate
      lastUpdated
      mscAgency
      vesselVoyage
    }
  }
}
"""

_GETDOCUMENT_RE = re.compile(
    r"""(?:data|href)=["']([^"']*?/myMSC/home/getdocument\?fileName=[^"'#]+)""",
    re.I,
)
_FILENAME_RE = re.compile(
    r"""id=["']filename["'][^>]*value=["']([^"']+\.pdf)["']""",
    re.I,
)
_FILENAME_REVERSED_RE = re.compile(
    r"""value=["']([^"']+\.pdf)["'][^>]*id=["']filename["']""",
    re.I,
)
_EMAIL_CLAIMS = (
    "email",
    "useremail",
    "user_email",
    "preferred_username",
    "unique_name",
    "upn",
)
_ROLE_CLAIMS = ("roles", "role", "userroles", "user_roles")
_USER_ID_CLAIMS = ("userid", "user_id", "user-id")

_BROWSER_FETCH_JS = """
async function(request) {
  const response = await fetch(request.url, {
    method: request.method || "GET",
    credentials: "include",
    headers: request.headers || {},
    body: request.body == null ? undefined : request.body
  });
  const blob = await response.blob();
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result || "");
    reader.onerror = () => reject(reader.error || new Error("读取响应失败"));
    reader.readAsDataURL(blob);
  });
  return {
    status: response.status,
    contentType: response.headers.get("content-type") || blob.type || "",
    dataUrl: String(dataUrl || "")
  };
}
""".strip()

_BROWSER_SESSION_JS = """
async function() {
  function readStore(store) {
    const values = {};
    try {
      for (let index = 0; index < store.length; index += 1) {
        const key = store.key(index);
        if (!key) continue;
        const lowered = key.toLowerCase();
        const ignored = ["shipper", "consignee", "notify", "party", "cargo"].some(
          (hint) => lowered.indexOf(hint) >= 0
        );
        const useful = ["user", "account", "profile", "auth"].some(
          (hint) => lowered.indexOf(hint) >= 0
        );
        if (ignored || !useful) continue;
        const value = store.getItem(key);
        if (!value || value.length > 8000) continue;
        values[key] = value;
      }
    } catch (error) {}
    return values;
  }
  const response = await fetch("https://www.mymsc.com/myMSC/token/getaccesstoken", {
    method: "GET",
    credentials: "include",
    headers: { "Accept": "*/*" }
  });
  return {
    href: location.href,
    origin: location.origin,
    userAgent: navigator.userAgent,
    localStorage: readStore(localStorage),
    sessionStorage: readStore(sessionStorage),
    status: response.status,
    contentType: response.headers.get("content-type") || "",
    text: await response.text()
  };
}
""".strip()


class SiDownloadMixin:
    """使用当前浏览器会话按单号下载拆并单草稿件。"""

    def download_draft_attachment(
        self: "FhtMscgwSiTask",
        booking_numbers: str,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> str:
        """按单号查询 FreeForm 列表并下载草稿件 PDF。

        booking_numbers 对应列表字段 bookingNumbers，拆并单可传逗号拼接的单号，
        `A, B` 与 `A,B` 视为同一单。只返回本地绝对路径，由调用方写入 attachments。
        """
        booking = _normalize_booking_numbers(booking_numbers)
        if not booking:
            raise BusinessError("草稿件单号不能为空")

        start, end = _resolve_date_range(from_date, to_date)
        self._require_browser_login()
        identity, access_token = self._read_browser_session()
        self.logger.info(f"开始通过浏览器接口下载草稿件：{booking}")

        item = self._find_free_form_item(
            booking=booking,
            from_date=start,
            to_date=end,
            identity=identity,
            access_token=access_token,
        )
        self.logger.info(f"查询草稿件数据")
        # 0 是官网合法 ID，不能用 or 把 0 当成空值。
        header_id = _required_id(item.get("headerId"), "headerId", booking)
        agency_id = _required_id(item.get("agencyId"), "agencyId", booking)
        # 下载接口使用列表原值，避免去掉空格后官网匹配失败。
        matched_booking_numbers = str(item.get("bookingNumbers") or "").strip() or booking

        file_url = self._request_document_url(
            booking_numbers=matched_booking_numbers,
            header_id=header_id,
            agency_id=agency_id,
        )
        self.logger.info(f"草稿件下载 URL：{file_url}")
        content = self._download_pdf(file_url)
        file_path = self._save_draft_pdf(content, matched_booking_numbers).resolve()
        self.logger.info(f"草稿件已下载：{file_path}")
        return str(file_path)

    def _require_browser_login(self: "FhtMscgwSiTask") -> None:
        """确认当前页面属于已登录的 myMSC。"""
        current_url = str(getattr(self.page, "url", "") or "")
        host = (urlparse(current_url).hostname or "").lower()
        if not host.endswith("mymsc.com"):
            raise BusinessError(f"当前页面不在 myMSC，无法读取浏览器登录态：{current_url}")

        cookies = list(self.page.cookies(all_domains=True) or [])
        logged_in = any(
            isinstance(cookie, dict) and cookie.get("name") == ".AspNet.Cookies" and cookie.get("value")
            for cookie in cookies
        )
        if not logged_in:
            raise BusinessError("浏览器中没有 MSC 登录 Cookie，请确认已完成自动化登录")

    def _read_browser_session(self: "FhtMscgwSiTask") -> tuple[dict[str, str], str]:
        """用浏览器 Cookie 换 AccessToken，并从浏览器会话补齐请求头。"""
        try:
            result = self.page.run_js(_BROWSER_SESSION_JS, timeout=_REQUEST_TIMEOUT)
        except (JavaScriptError, TimeoutError, RuntimeError) as exc:
            raise BusinessError(f"读取浏览器登录信息失败：{exc}") from exc
        if not isinstance(result, dict):
            raise BusinessError("读取浏览器登录信息失败：无有效响应")

        status = int(result.get("status") or 0)
        body = str(result.get("text") or "")
        if status in {401, 403}:
            raise BusinessError("浏览器登录态已失效，无法获取 AccessToken")
        if status >= 400 or status == 0:
            raise BusinessError(f"获取 AccessToken 失败：HTTP {status} {_brief(body)}")

        try:
            token_payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise BusinessError(f"AccessToken 响应不是 JSON：{_brief(body)}") from exc
        if not isinstance(token_payload, dict) or not token_payload.get("Authenticated"):
            raise BusinessError("AccessToken 无效，浏览器登录态不可用")

        access_token = str(token_payload.get("AccessToken") or "").strip()
        if not access_token:
            raise BusinessError("浏览器未返回 AccessToken")

        identity = _build_identity(
            token_payload=token_payload,
            jwt_payload=_decode_jwt_payload(access_token),
            storage={
                **(result.get("localStorage") or {}),
                **(result.get("sessionStorage") or {}),
            },
            fallback_email=str(self.website_info.get("websiteAccount") or "").strip(),
        )
        if not identity["email"]:
            raise BusinessError("浏览器和任务账号都没有可用的用户邮箱，无法查询草稿件")
        self.logger.info(
            f"已读取浏览器登录态：账号={identity['email']} 角色={identity['roles']}"
        )
        return identity, access_token

    def _find_free_form_item(
        self: "FhtMscgwSiTask",
        *,
        booking: str,
        from_date: str,
        to_date: str,
        identity: dict[str, str],
        access_token: str,
    ) -> dict[str, Any]:
        """查询 FreeForm 列表并按规范化后的单号精确匹配。"""
        payload = {
            "query": _FREE_FORM_LIST_QUERY,
            "variables": {"fromDate": from_date, "toDate": to_date},
            "operationName": "GetFreeFormeSiList",
        }
        response = self._browser_request(
            "POST",
            _DASHBOARD_GRAPHQL,
            headers=_auth_headers(identity, access_token),
            body=json.dumps(payload, ensure_ascii=False),
        )
        _raise_for_http(response, "查询草稿件列表")
        try:
            data = json.loads(response["text"])
        except json.JSONDecodeError as exc:
            raise BusinessError(f"草稿件列表响应不是 JSON：{_brief(response['text'])}") from exc
        if isinstance(data, dict) and data.get("errors"):
            message = _graphql_error_message(data.get("errors"))
            raise BusinessError(f"查询草稿件列表失败：{message}")

        items = (((data or {}).get("data") or {}).get("freeFormeSiList") or {}).get("items")
        if not isinstance(items, list):
            raise BusinessError("草稿件列表响应缺少 data.freeFormeSiList.items")

        for item in items:
            if not isinstance(item, dict):
                continue
            if _normalize_booking_numbers(item.get("bookingNumbers")) == booking:
                return item
        raise BusinessError(f"{from_date} 至 {to_date} 的草稿件列表中查不到单号：{booking}")

    def _request_document_url(
        self: "FhtMscgwSiTask",
        *,
        booking_numbers: str,
        header_id: str,
        agency_id: str,
    ) -> str:
        """提交官网下载表单，并从 HTML 中解析 PDF 地址。"""
        form = urlencode_form(
            {
                "headerId": header_id,
                "bookingNumber": booking_numbers,
                "agencyId": agency_id,
            }
        )
        response = self._browser_request(
            "POST",
            _SHOW_FREE_FORM_SI_URL,
            headers={
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
            body=form,
        )
        _raise_for_http(response, "获取草稿件下载地址")
        file_url = _extract_getdocument_url(response["text"])
        if not file_url:
            raise BusinessError(f"草稿件响应中没有下载地址：{_brief(response['text'])}")
        return file_url

    def _download_pdf(self: "FhtMscgwSiTask", file_url: str) -> bytes:
        """通过浏览器下载 PDF，并校验内容。"""
        response = self._browser_request(
            "GET",
            file_url,
            headers={"Accept": "application/pdf,application/octet-stream,*/*;q=0.8"},
        )
        _raise_for_http(response, "下载草稿件")
        content = response["content"]
        content_type = response["content_type"]
        if not content:
            raise BusinessError("草稿件下载结果为空")
        if "pdf" not in content_type.lower() and not content.startswith(b"%PDF"):
            raise BusinessError(
                f"草稿件返回的不是 PDF：{content_type or 'unknown'} {_brief(response['text'])}"
            )
        return content

    def _save_draft_pdf(self: "FhtMscgwSiTask", content: bytes, booking_numbers: str) -> Path:
        """把 PDF 保存到任务下载目录。"""
        download_dir = getattr(self.dom, "download_dir", None) or self.browser_manager.settings.download_dir
        queue_name = self.context.queue_name or "MSCGW"
        directory = Path(download_dir) / queue_name
        directory.mkdir(parents=True, exist_ok=True)
        safe_booking = re.sub(r"[^A-Za-z0-9_-]+", "_", booking_numbers).strip("_") or "draft"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = directory / f"{safe_booking}_{timestamp}.pdf"
        file_path.write_bytes(content)
        return file_path

    def _browser_request(
        self: "FhtMscgwSiTask",
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: str | None = None,
    ) -> dict[str, Any]:
        """在已打开的浏览器中发请求，自动携带当前页面的 Cookie。"""
        request = {
            "method": method.upper(),
            "url": url,
            "headers": headers or {},
            "body": body,
        }
        try:
            result = self.page.run_js(_BROWSER_FETCH_JS, request, timeout=_REQUEST_TIMEOUT)
        except (JavaScriptError, TimeoutError, RuntimeError) as exc:
            raise BusinessError(f"浏览器请求失败：{method.upper()} {url}，{exc}") from exc
        if not isinstance(result, dict):
            raise BusinessError(f"浏览器请求无有效响应：{method.upper()} {url}")

        content = _decode_data_url(str(result.get("dataUrl") or ""))
        text = content.decode("utf-8", errors="replace")
        return {
            "status": int(result.get("status") or 0),
            "content_type": str(result.get("contentType") or ""),
            "content": content,
            "text": text,
        }



def _required_id(value: Any, name: str, booking: str) -> str:
    """缺失才算没有 ID；0 要原样传给下载接口。"""
    if value is None or str(value).strip() == "":
        raise BusinessError(f"单号 {booking} 缺少 {name}，无法下载草稿件")
    return str(value).strip()


def _normalize_booking_numbers(value: Any) -> str:
    """规范化单号，兼容逗号两侧的空格。"""
    parts = [part.strip() for part in str(value or "").split(",") if part.strip()]
    return ",".join(parts)


def _resolve_date_range(from_date: str | None, to_date: str | None) -> tuple[str, str]:
    """默认查询今天往前 60 天，即近 2 个月。"""
    end = _parse_date(to_date) if to_date else date.today()
    start = _parse_date(from_date) if from_date else end - timedelta(days=_LIST_LOOKBACK_DAYS)
    if start > end:
        raise BusinessError("草稿件查询开始日期不能晚于结束日期")
    return start.isoformat(), end.isoformat()


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise BusinessError(f"日期格式必须是 YYYY-MM-DD：{value}") from exc


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """只解析 JWT 载荷，不校验签名；用于补齐浏览器里的用户头。"""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _build_identity(
    *,
    token_payload: dict[str, Any],
    jwt_payload: dict[str, Any],
    storage: dict[str, Any],
    fallback_email: str,
) -> dict[str, str]:
    """优先使用浏览器返回的邮箱、角色和用户 ID。"""
    pairs = _identity_pairs(token_payload, jwt_payload, storage)
    email = _first_email(pairs)
    if not email and "@" in fallback_email:
        email = fallback_email
    roles = _first_roles(pairs) or "Customer"
    user_id = _first_claim(pairs, _USER_ID_CLAIMS)
    if "@" in user_id:
        user_id = ""
    return {"email": email, "roles": roles, "user_id": user_id}


def _identity_pairs(*sources: dict[str, Any]) -> list[tuple[str, Any]]:
    pairs: list[tuple[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            pairs.append((str(key), value))
            if isinstance(value, str) and value.strip()[:1] in "{[":
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    pairs.extend((str(parsed_key), parsed_value) for parsed_key, parsed_value in parsed.items())
    return pairs


def _first_email(pairs: list[tuple[str, Any]]) -> str:
    wanted = {name.lower() for name in _EMAIL_CLAIMS}
    for key, value in pairs:
        if key.lower() not in wanted or not isinstance(value, str):
            continue
        candidate = value.strip()
        if "@" in candidate:
            return candidate
    return ""


def _first_claim(pairs: list[tuple[str, Any]], names: tuple[str, ...]) -> str:
    wanted = {name.lower() for name in names}
    for key, value in pairs:
        if key.lower() not in wanted:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
    return ""


def _first_roles(pairs: list[tuple[str, Any]]) -> str:
    for key, value in pairs:
        if key.lower() not in _ROLE_CLAIMS:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            texts = [str(item).strip() for item in value if str(item).strip()]
            if "Customer" in texts:
                return "Customer"
            if texts:
                return ",".join(texts)
    return ""


def _auth_headers(identity: dict[str, str], access_token: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "graphql-preflight": "1",
        "mymsc-user-email": identity["email"],
        "mymsc-user-roles": identity["roles"],
        "mymsc-impersonated-user-email": "",
        "mymsc-impersonated-user-id": "",
    }
    if identity.get("user_id"):
        headers["mymsc-user-id"] = identity["user_id"]
    return headers


def urlencode_form(form: dict[str, str]) -> str:
    """按 application/x-www-form-urlencoded 编码，保留单号中的空格语义。"""
    return urlencode(form)


def _extract_getdocument_url(html: str) -> str | None:
    """从 ShowFreeFormSiWithoutBlNumber 的 HTML 中截取 PDF 地址。"""
    text = unescape(html or "")
    match = _GETDOCUMENT_RE.search(text)
    if match:
        path = match.group(1).strip().split("#", 1)[0]
        return urljoin(_BASE_URL, path)

    for pattern in (_FILENAME_RE, _FILENAME_REVERSED_RE):
        match = pattern.search(text)
        if match:
            return urljoin(_BASE_URL, f"/myMSC/home/getdocument?fileName={match.group(1)}")
    return None


def _decode_data_url(data_url: str) -> bytes:
    header, separator, payload = data_url.partition(",")
    if not separator:
        return b""
    if ";base64" in header:
        try:
            return base64.b64decode(payload)
        except ValueError:
            return b""
    return payload.encode("utf-8")


def _raise_for_http(response: dict[str, Any], action: str) -> None:
    status = int(response.get("status") or 0)
    if status in {401, 403}:
        raise BusinessError(f"{action}鉴权失败：HTTP {status}，浏览器登录态可能已失效")
    if status == 0 or status >= 400:
        raise BusinessError(f"{action}失败：HTTP {status} {_brief(str(response.get('text') or ''))}")


def _graphql_error_message(errors: Any) -> str:
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict) and first.get("message"):
            return str(first["message"])
    return _brief(str(errors))


def _brief(text: str, limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."
