"""MSCGW 拆并单草稿件协议直连下载(备用方案)。

复用当前 MSCGW 自动化浏览器的会话 Cookie 直连官网接口,不处理登录:
  1. GET /myMSC/token/getaccesstoken  用站点 Cookie 兑换业务 AccessToken
  2. POST services.mymsc.com/dashboard/graphql  查询 FreeForm eSI 列表
  3. POST /myMSC/Dashboard/ShowFreeFormSiWithoutBlNumber  换取含下载链接的 HTML
  4. GET /myMSC/home/getdocument  下载 PDF,落盘后加入 self.attachments
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urljoin

import requests

from app.core.task.errors import BusinessError
from app.spider.MSCGW.selectors import DASHBOARD_GRAPHQL_API

if TYPE_CHECKING:
    from app.spider.MSCGW.tasks.fht_mscgw_si import FhtMscgwSiTask

MSC_BASE_URL = "https://www.mymsc.com"
GET_ACCESS_TOKEN_URL = f"{MSC_BASE_URL}/myMSC/token/getaccesstoken"
WELCOME_PAGE_URL = f"{MSC_BASE_URL}/myMSC/welcome"
SHOW_FREE_FORM_SI_URL = f"{MSC_BASE_URL}/myMSC/Dashboard/ShowFreeFormSiWithoutBlNumber"
FREE_FORM_ESI_REFERER = f"{MSC_BASE_URL}/myMSC/dashboard/free-form-esi"

MSC_USER_ROLES = "Customer"
MSC_HTTP_TIMEOUT = 30
# 草稿件在保存动作后立刻查询,近几天的窗口足以覆盖;排查历史问题时可放大。
FREE_FORM_LIST_WINDOW_DAYS = 7

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

GET_FREE_FORM_ESI_LIST_QUERY = """
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


class SiDownloadMixin:
    """拆并单草稿件协议直连下载,复用当前浏览器会话(不处理登录)。"""

    @staticmethod
    def _normalize_msc_booking_numbers(value: Any) -> str:
        """规范化 bookingNumbers,兼容 `A, B` 与 `A,B` 的空格差异。"""
        parts = [part.strip() for part in str(value or "").split(",") if part.strip()]
        return ",".join(parts)

    def _msc_user_agent(self: "FhtMscgwSiTask") -> str:
        """优先使用当前浏览器真实 UA,保证请求头与会话指纹一致。"""
        return str(getattr(self.page, "user_agent", "") or DEFAULT_USER_AGENT)

    def _msc_browser_cookies(self: "FhtMscgwSiTask") -> dict[str, str]:
        """提取当前浏览器 mymsc.com 会话 Cookie。"""
        url = str(getattr(self.page, "url", "") or "")
        if "mymsc.com" not in url:
            raise BusinessError(f"当前页面不在 mymsc.com 域,无法提取 MSC 会话 Cookie:{url}")

        cookies: dict[str, str] = {}
        for cookie in self.page.cookies():
            # DrissionPage cookies() 返回 [{name, value, domain}, ...]
            if isinstance(cookie, dict) and cookie.get("name"):
                cookies[str(cookie["name"])] = str(cookie.get("value") or "")
        if not any(name.startswith(".AspNet") for name in cookies):
            self.logger.warn("MSC 浏览器 Cookie 中未见 .AspNet 系列字段,会话可能已失效")
        return cookies

    def _msc_get_access_token(self: "FhtMscgwSiTask", cookies: dict[str, str]) -> str:
        """用站点 Cookie 兑换业务 AccessToken(令牌兑换,非登录动作)。"""
        resp = requests.get(
            GET_ACCESS_TOKEN_URL,
            cookies=cookies,
            headers={
                "User-Agent": self._msc_user_agent(),
                "Accept": "*/*",
                "Referer": WELCOME_PAGE_URL,
            },
            timeout=MSC_HTTP_TIMEOUT,
        )
        if resp.status_code in {401, 403}:
            raise BusinessError(
                f"MSC 获取 AccessToken 被拒绝(HTTP {resp.status_code}),会话可能失效或出口被风控"
            )
        content_type = str(resp.headers.get("Content-Type") or "")
        if "application/json" not in content_type.lower():
            # 会话失效时该接口会重定向到登录页,拿到的是 HTML
            raise BusinessError(
                f"MSC AccessToken 响应非 JSON(HTTP {resp.status_code}, {content_type}),会话可能已失效"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise BusinessError("MSC AccessToken 响应解析失败") from exc

        token = str((data or {}).get("AccessToken") or "")
        if not (data or {}).get("Authenticated") or not token:
            raise BusinessError("MSC AccessToken 无效,会话可能已失效")
        self.logger.info("MSC AccessToken 兑换成功")
        return token

    def _msc_query_free_form_esi(
        self: "FhtMscgwSiTask",
        booking_numbers: str,
        *,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """查询 FreeForm eSI 列表并按 bookingNumbers 匹配,返回最新一条 item。

        Args:
            booking_numbers: 订舱号,兼容逗号拼接的拆并单多单号。
            from_date: 起始日期 YYYY-MM-DD,默认近 FREE_FORM_LIST_WINDOW_DAYS 天。
            to_date: 结束日期 YYYY-MM-DD,默认今天。

        Returns:
            匹配的 item dict(headerId/agencyId/bookingNumbers/status 等);未匹配返回 None。
        """
        booking = self._normalize_msc_booking_numbers(booking_numbers)
        if not booking:
            raise BusinessError("查询 FreeForm eSI 列表失败:bookingNumbers 不能为空")

        account = str(self.website_info.get("websiteAccount") or "").strip()
        cookies = self._msc_browser_cookies()
        token = self._msc_get_access_token(cookies)

        today = date.today()
        end = to_date or today.isoformat()
        start = from_date or (today - timedelta(days=FREE_FORM_LIST_WINDOW_DAYS)).isoformat()

        resp = requests.post(
            DASHBOARD_GRAPHQL_API,
            json={
                "query": GET_FREE_FORM_ESI_LIST_QUERY,
                "variables": {"fromDate": start, "toDate": end},
                "operationName": "GetFreeFormeSiList",
            },
            headers={
                "User-Agent": self._msc_user_agent(),
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Origin": "https://www.mymsc.com",
                "Referer": "https://www.mymsc.com/",
                "graphql-preflight": "1",
                "mymsc-user-email": account,
                "mymsc-user-roles": MSC_USER_ROLES,
                "mymsc-impersonated-user-email": "",
                "mymsc-impersonated-user-id": "",
            },
            timeout=MSC_HTTP_TIMEOUT,
        )
        if resp.status_code in {401, 403}:
            raise BusinessError(
                f"GetFreeFormeSiList 鉴权失败(HTTP {resp.status_code}),token 无效或出口被风控"
            )
        if resp.status_code >= 400:
            body = resp.text[:200]
            raise BusinessError(f"GetFreeFormeSiList 请求失败(HTTP {resp.status_code}):{body}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise BusinessError("GetFreeFormeSiList 响应非 JSON") from exc
        if isinstance(data, dict) and data.get("errors"):
            errors_text = str(data.get("errors"))[:300]
            raise BusinessError(f"GetFreeFormeSiList GraphQL 返回 errors:{errors_text}")

        items = (
            (((data or {}).get("data") or {}).get("freeFormeSiList") or {}).get("items")
            if isinstance(data, dict)
            else None
        )
        if items is None:
            raw_text = str(data)[:300]
            raise BusinessError(f"GetFreeFormeSiList 响应缺少 data.freeFormeSiList.items:{raw_text}")

        self.logger.info(f"FreeForm eSI 列表查询成功,窗口 {start}~{end},共 {len(items)} 条")
        matched = [
            item
            for item in items
            if self._normalize_msc_booking_numbers(item.get("bookingNumbers")) == booking
        ]
        if not matched:
            self.logger.warn(f"FreeForm eSI 列表未匹配到单号:{booking}")
            return None

        # 同一单号历史上可能保存过多份草稿,取 lastUpdated/originalCreateDate 最新的一条
        latest = max(
            matched,
            key=lambda item: str(item.get("lastUpdated") or item.get("originalCreateDate") or ""),
        )
        self.logger.info(
            f"FreeForm eSI 匹配 {len(matched)} 条,取最新一条:"
            f"headerId={latest.get('headerId')} agencyId={latest.get('agencyId')} "
            f"bookingNumbers={latest.get('bookingNumbers')} status={latest.get('status')} "
            f"lastUpdated={latest.get('lastUpdated')}"
        )
        return latest

    def _msc_show_free_form_si(
        self: "FhtMscgwSiTask",
        cookies: dict[str, str],
        item: dict[str, Any],
        booking: str,
    ) -> str:
        """POST ShowFreeFormSiWithoutBlNumber,返回含 getdocument 链接的 HTML。

        bookingNumber 必须回传官网列表原值(保留逗号后的空格),归一化值会导致查询失败。
        """
        header_id = str(item.get("headerId") or "").strip()
        agency_id = str(item.get("agencyId") or "").strip()
        if not header_id or not agency_id:
            raise BusinessError(f"FreeForm eSI 记录缺少 headerId/agencyId:{item}")
        original_booking = str(item.get("bookingNumbers") or "").strip() or booking

        resp = requests.post(
            SHOW_FREE_FORM_SI_URL,
            cookies=cookies,
            data={
                "headerId": header_id,
                "bookingNumber": original_booking,
                "agencyId": agency_id,
            },
            headers={
                "User-Agent": self._msc_user_agent(),
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": MSC_BASE_URL,
                "Referer": FREE_FORM_ESI_REFERER,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=MSC_HTTP_TIMEOUT,
        )
        html = resp.text or ""
        if resp.status_code in {401, 403}:
            raise BusinessError(
                f"ShowFreeFormSiWithoutBlNumber 鉴权失败(HTTP {resp.status_code}):{html[:300]}"
            )
        if resp.status_code >= 400:
            raise BusinessError(
                f"ShowFreeFormSiWithoutBlNumber 请求失败(HTTP {resp.status_code}):{html[:300]}"
            )
        return html

    @staticmethod
    def _extract_getdocument_url(html: str) -> Optional[str]:
        """从 ShowFreeFormSiWithoutBlNumber 的 HTML 中截取 getdocument 链接。"""
        text = html or ""
        match = re.search(
            r'(?:data|href)=["\']([^"\']*?/myMSC/home/getdocument\?fileName=[^"\'#]+)',
            text,
            flags=re.I,
        )
        if not match:
            # 兜底:隐藏域 id="filename" 中的 PDF 文件名
            match = re.search(
                r'id=["\']filename["\'][^>]*value=["\']([^"\']+\.pdf)["\']',
                text,
                flags=re.I,
            )
            if match:
                return urljoin(MSC_BASE_URL, f"/myMSC/home/getdocument?fileName={match.group(1)}")
            return None

        path = match.group(1).strip()
        # object data 可能带 #navpanes 片段,下载时去掉
        path = path.split("#", 1)[0]
        return urljoin(MSC_BASE_URL, path)

    def _msc_download_pdf(self: "FhtMscgwSiTask", cookies: dict[str, str], file_url: str) -> bytes:
        """下载 getdocument PDF 并校验为有效 PDF,返回文件字节。"""
        resp = requests.get(
            file_url,
            cookies=cookies,
            headers={
                "User-Agent": self._msc_user_agent(),
                "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
                "Referer": FREE_FORM_ESI_REFERER,
            },
            timeout=MSC_HTTP_TIMEOUT,
            allow_redirects=True,
        )
        content = resp.content or b""
        content_type = str(resp.headers.get("Content-Type") or "").lower()
        if resp.status_code in {401, 403}:
            raise BusinessError(f"FreeForm eSI 下载鉴权失败(HTTP {resp.status_code}):{file_url}")
        if resp.status_code >= 400:
            body = (resp.text or "")[:200]
            raise BusinessError(f"FreeForm eSI 下载失败(HTTP {resp.status_code}):{body}")
        if not content:
            raise BusinessError(f"FreeForm eSI 返回空内容:{file_url}")
        if "pdf" not in content_type and not content.startswith(b"%PDF"):
            body = (resp.text or "")[:200]
            raise BusinessError(f"FreeForm eSI 返回非 PDF({content_type or 'unknown'}):{body}")
        return content

    def _down_spill_attachments(self: "FhtMscgwSiTask", booking_numbers: Optional[str] = None) -> str:
        """拆并单草稿件协议直连下载,落盘后加入 self.attachments,返回本地文件路径。

        依赖当前浏览器已登录 MSC(页面在 mymsc.com 域),本方法不做任何登录/会话续期;
        下载的 PDF 由 get_attachments() 统一上传 OSS,与预览下载的附件走同一通道。
        """
        raw = booking_numbers if booking_numbers is not None else self.content.get("carrierBookingNumber")
        booking = self._normalize_msc_booking_numbers(raw)
        if not booking:
            raise BusinessError("下载拆并单草稿件失败:bookingNumbers 不能为空")

        cookies = self._msc_browser_cookies()
        item = self._msc_query_free_form_esi(raw)
        if item is None:
            raise BusinessError(f"FreeForm eSI 列表未匹配到单号 {booking},无法下载草稿件")

        html = self._msc_show_free_form_si(cookies, item, booking)
        file_url = self._extract_getdocument_url(html)
        if not file_url:
            raise BusinessError(
                f"ShowFreeFormSiWithoutBlNumber 响应未解析到 getdocument 链接:"
                f"headerId={item.get('headerId')} html={html[:300]}"
            )
        content = self._msc_download_pdf(cookies, file_url)

        # 与 click_to_download 默认目录一致:runtime/downloads/{queue_name}/
        save_dir = Path(self.dom.download_dir or ".") / (
            self.dom.queue_name or self.context.queue_name or "MSCGW"
        )
        save_dir.mkdir(parents=True, exist_ok=True)
        file_path = save_dir / f"{self._build_draft_file_stem()}.pdf"
        file_path.write_bytes(content)

        self.attachments.append(str(file_path))
        self.logger.info(
            f"FreeForm eSI 草稿件下载完成:{file_path}({len(content)} 字节),已加入 attachments"
        )
        return str(file_path)
