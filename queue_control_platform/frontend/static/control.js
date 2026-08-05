const deviceList = document.getElementById("device-list");
const queueList = document.getElementById("queue-list");
const assignmentDevice = document.getElementById("assignment-device");
const notice = document.getElementById("notice");
let noticeTimer;
const DEVICE_STATE_LABELS = Object.freeze({
  ONLINE: "在线",
  OFFLINE: "离线",
});
const QUEUE_STATE_LABELS = Object.freeze({
  STARTING: "启动中",
  RUNNING: "运行中",
  DRAINING: "排空中",
  PAUSED: "已暂停",
  RESTARTING: "重启中",
  FAILED: "启动失败",
  UNREPORTED: "等待上报",
  REMOVED: "已解除",
});

// 短暂显示用户操作结果和 API 返回错误。
function message(text) {
  notice.textContent = text;
  notice.classList.add("visible");
  window.clearTimeout(noticeTimer);
  noticeTimer = window.setTimeout(() => notice.classList.remove("visible"), 5000);
}

// 对接口返回文本进行 HTML 转义，避免动态数据注入页面结构。
function escapeHtml(value) {
  const node = document.createElement("span");
  node.textContent = value || "";
  return node.innerHTML;
}

// 调用 JSON API，并将非成功响应转换为可展示的异常。
async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "操作未完成");
  return payload;
}

// 根据设备在线状态生成状态文本样式。
function deviceState(status) {
  const code = String(status || "OFFLINE").toUpperCase();
  const normalized = code.toLowerCase();
  const label = DEVICE_STATE_LABELS[code] || "未知状态";
  return `<span class="device-${escapeHtml(normalized)}">${escapeHtml(label)}</span>`;
}

// 根据队列状态生成用于表格展示的状态标签。
function queueState(state) {
  const code = String(state || "UNREPORTED").toUpperCase();
  const normalized = code.toLowerCase();
  const label = QUEUE_STATE_LABELS[code] || "未知状态";
  return `<span class="state state-${escapeHtml(normalized)}">${escapeHtml(label)}</span>`;
}

// 生成带设备与队列上下文的维护操作按钮。
function actionButton(label, action, deviceId, queueName, disabled = false, style = "") {
  return `<button type="button" class="${style}" data-action="${action}" data-device="${escapeHtml(deviceId)}" data-queue="${escapeHtml(queueName || "")}" ${disabled ? "disabled" : ""}>${label}</button>`;
}

// 将 MySQL 中的设备和队列状态渲染为维护表格。
function render(dashboard) {
  const { devices, queues } = dashboard;
  assignmentDevice.innerHTML = devices.map((device) => `<option value="${escapeHtml(device.deviceId)}">${escapeHtml(device.deviceId)} - ${escapeHtml(device.displayName)}</option>`).join("");
  deviceList.innerHTML = devices.map((device) => `<tr>
    <td><strong>${escapeHtml(device.deviceId)}</strong></td>
    <td>${escapeHtml(device.displayName)}</td>
    <td>${deviceState(device.status)}</td>
    <td>${escapeHtml(device.lastSeenAt || "-")}</td>
    <td class="actions">${actionButton("重启该设备全部队列", "restart-all", device.deviceId, "", device.status !== "ONLINE", "neutral")}</td>
  </tr>`).join("");
  queueList.innerHTML = queues.map((queue) => {
    const paused = queue.state === "PAUSED";
    const busy = ["DRAINING", "RESTARTING"].includes(queue.state);
    const offline = !devices.some((device) => device.deviceId === queue.deviceId && device.status === "ONLINE");
    const changes = queue.sourceChanges.length ? queue.sourceChanges.join("\n") : "-";
    return `<tr>
      <td>${escapeHtml(queue.deviceId)}</td>
      <td><strong>${escapeHtml(queue.queueName)}</strong></td>
      <td>${queueState(queue.state)}</td>
      <td>${escapeHtml(queue.pid || "-")}</td>
      <td class="changes">${escapeHtml(changes)}</td>
      <td class="error">${escapeHtml(queue.lastError || "-")}</td>
      <td><div class="actions">
        ${actionButton("暂停", "pause", queue.deviceId, queue.queueName, offline || paused || busy)}
        ${actionButton("恢复", "resume", queue.deviceId, queue.queueName, offline || !paused)}
        ${actionButton("重启", "restart", queue.deviceId, queue.queueName, offline || busy)}
        ${actionButton("解除", "unassign", queue.deviceId, queue.queueName, offline, "danger")}
      </div></td>
    </tr>`;
  }).join("");
}

// 读取中心平台快照并更新页面的全部状态区域。
async function refresh() {
  try {
    render(await api("/api/dashboard", { cache: "no-store" }));
    document.getElementById("updated-at").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN")}`;
  } catch (error) {
    message(`无法读取平台状态：${error.message}`);
  }
}

// 提交设备创建表单，并展示一次性注册令牌。
document.getElementById("device-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    const result = await api("/api/devices", {
      method: "POST",
      body: JSON.stringify({ deviceId: form.get("deviceId"), displayName: form.get("displayName") }),
    });
    document.getElementById("enrollment-token").textContent = result.enrollmentToken;
    document.getElementById("enrollment-result").hidden = false;
    event.currentTarget.reset();
    message("设备已创建，请将注册令牌配置到目标机器。");
    await refresh();
  } catch (error) {
    message(error.message);
  }
});

// 提交队列分配表单，并向所选设备发送监听命令。
document.getElementById("assignment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    await api(`/api/devices/${encodeURIComponent(form.get("deviceId"))}/queues`, {
      method: "POST",
      body: JSON.stringify({ queueName: form.get("queueName") }),
    });
    event.currentTarget.reset();
    message("队列已分配，等待目标设备接收命令。");
    await refresh();
  } catch (error) {
    message(error.message);
  }
});

// 分派表格内的队列控制与设备全部重启操作。
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const { action, device, queue } = button.dataset;
  try {
    if (action === "restart-all") {
      await api(`/api/devices/${encodeURIComponent(device)}/commands/restart-all`, { method: "POST" });
    } else if (action === "unassign") {
      await api(`/api/devices/${encodeURIComponent(device)}/queues/${encodeURIComponent(queue)}`, { method: "DELETE" });
    } else {
      await api(`/api/devices/${encodeURIComponent(device)}/queues/${encodeURIComponent(queue)}/commands`, {
        method: "POST",
        body: JSON.stringify({ action }),
      });
    }
    message("命令已投递，等待设备状态上报。");
    await refresh();
  } catch (error) {
    message(error.message);
  }
});

refresh();
window.setInterval(refresh, 2000);
