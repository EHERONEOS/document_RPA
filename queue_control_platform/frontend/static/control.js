const deviceList = document.getElementById("device-list");
const queueList = document.getElementById("queue-list");
const assignmentDevice = document.getElementById("assignment-device");
const notice = document.getElementById("notice");
const flowSelect = document.getElementById("flow-select");
const flowSteps = document.getElementById("flow-steps");
const flowList = document.getElementById("flow-list");
let noticeTimer;
let flows = [];
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

function stepRow(type = "action") {
  const row = document.createElement("div");
  row.className = "flow-step";
  row.dataset.type = type;
  row.innerHTML = type === "action" ? `
    <label>步骤 ID<input class="step-id" value="action.step" maxlength="128" autocomplete="off"></label>
    <label>动作<input class="step-action" value="MSCGW.login" maxlength="128" autocomplete="off"></label>
    <label>输入 JSON<input class="step-inputs" value="{}" autocomplete="off"></label>
    <button type="button" class="danger remove-flow-step">移除</button>` : `
    <label>步骤 ID<input class="step-id" value="checkpoint.before_save" maxlength="128" autocomplete="off"></label>
    <label>检查点 ID<input class="checkpoint-id" value="checkpoint.before_save" maxlength="128" autocomplete="off"></label>
    <button type="button" class="danger remove-flow-step">移除</button>`;
  flowSteps.append(row);
}

function collectSteps() {
  return [...flowSteps.querySelectorAll(".flow-step")].map((row) => {
    const stepId = row.querySelector(".step-id").value.trim();
    if (row.dataset.type === "checkpoint") {
      return { type: "checkpoint", stepId, checkpointId: row.querySelector(".checkpoint-id").value.trim() || undefined };
    }
    let inputs;
    try {
      inputs = JSON.parse(row.querySelector(".step-inputs").value || "{}");
    } catch (_) {
      throw new Error(`步骤 ${stepId || "-"} 的输入不是有效 JSON`);
    }
    if (!inputs || Array.isArray(inputs) || typeof inputs !== "object") throw new Error(`步骤 ${stepId || "-"} 的输入必须是对象`);
    return { type: "action", stepId, action: row.querySelector(".step-action").value.trim(), inputs };
  });
}

function selectedFlowId() {
  return flowSelect.value || document.getElementById("flow-id").value.trim();
}

function renderFlows() {
  const current = flowSelect.value;
  flowSelect.innerHTML = flows.map((flow) => `<option value="${escapeHtml(flow.flowId)}">${escapeHtml(flow.displayName)} (${escapeHtml(flow.flowId)})</option>`).join("");
  if (flows.some((flow) => flow.flowId === current)) flowSelect.value = current;
  flowList.innerHTML = flows.map((flow) => `<tr>
    <td><strong>${escapeHtml(flow.displayName)}</strong><br><small>${escapeHtml(flow.flowId)}</small></td>
    <td>${escapeHtml(flow.currentVersion || "未发布")}</td>
    <td>${escapeHtml(flow.lastReleasedAt || "-")}</td>
    <td class="actions">${flow.currentVersion ? `<button type="button" data-flow-action="rollback" data-flow="${escapeHtml(flow.flowId)}" data-version="${escapeHtml(flow.currentVersion)}" class="neutral">回滚到此版本</button>` : "-"}</td>
  </tr>`).join("");
  document.getElementById("flow-summary").textContent = `${flows.length} 个流程`;
}

async function refreshFlows() {
  const result = await api("/api/flows", { cache: "no-store" });
  flows = result.flows;
  renderFlows();
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
    return `<tr>
      <td>${escapeHtml(queue.deviceId)}</td>
      <td><strong>${escapeHtml(queue.queueName)}</strong></td>
      <td>${queueState(queue.state)}</td>
      <td>${escapeHtml(queue.pid || "-")}</td>
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
    const [dashboard] = await Promise.all([api("/api/dashboard", { cache: "no-store" }), refreshFlows()]);
    render(dashboard);
    document.getElementById("updated-at").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN")}`;
  } catch (error) {
    message(`无法读取平台状态：${error.message}`);
  }
}

document.getElementById("add-action-step").addEventListener("click", () => stepRow("action"));
document.getElementById("add-checkpoint-step").addEventListener("click", () => stepRow("checkpoint"));
flowSteps.addEventListener("click", (event) => event.target.closest(".remove-flow-step")?.closest(".flow-step")?.remove());

document.getElementById("flow-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    await api("/api/flows", { method: "POST", body: JSON.stringify(Object.fromEntries(form)) });
    message("流程已创建，可以编辑并保存版本。");
    await refreshFlows();
    flowSelect.value = form.get("flowId");
  } catch (error) { message(error.message); }
});

document.getElementById("save-version").addEventListener("click", async () => {
  const flowId = selectedFlowId();
  const flow = flows.find((item) => item.flowId === flowId);
  const flowVersion = document.getElementById("flow-version").value.trim();
  try {
    if (!flow) throw new Error("请先创建并选择流程");
    const definition = {
      schemaVersion: 1, flowId, flowVersion, name: flow.displayName,
      description: flow.description || undefined, steps: collectSteps(),
    };
    if (!definition.steps.length) throw new Error("流程至少需要一个步骤");
    await api(`/api/flows/${encodeURIComponent(flowId)}/versions/${encodeURIComponent(flowVersion)}`, {
      method: "POST", body: JSON.stringify({ definition }),
    });
    message("流程版本已通过 Schema 校验并保存。");
    await refreshFlows();
  } catch (error) { message(error.message); }
});

document.getElementById("flow-release-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const flowId = selectedFlowId();
  const flowVersion = document.getElementById("flow-version").value.trim();
  const form = new FormData(event.currentTarget);
  try {
    if (!flows.some((flow) => flow.flowId === flowId)) throw new Error("请先选择流程");
    const mode = String(form.get("mode"));
    let strategy = { mode };
    if (mode === "devices") strategy.deviceIds = String(form.get("deviceIds") || "").split(",").map((item) => item.trim()).filter(Boolean);
    if (mode === "percentage") strategy.percentage = Number(form.get("percentage"));
    await api("/api/flow-bindings", { method: "POST", body: JSON.stringify({ queueName: form.get("queueName"), flowId }) });
    const result = await api(`/api/flows/${encodeURIComponent(flowId)}/releases`, {
      method: "POST", body: JSON.stringify({ flowVersion, strategy, releaseNote: form.get("releaseNote") }),
    });
    message(`发布已投递到 ${result.targetDevices.length} 个设备。`);
    await refreshFlows();
  } catch (error) { message(error.message); }
});

flowList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-flow-action]");
  if (!button || button.dataset.flowAction !== "rollback") return;
  const targetVersion = window.prompt("目标版本", button.dataset.version);
  if (!targetVersion) return;
  try {
    await api(`/api/flows/${encodeURIComponent(button.dataset.flow)}/rollback`, {
      method: "POST", body: JSON.stringify({ targetVersion, strategy: { mode: "all" } }),
    });
    message("回滚已发布并同步到目标设备。");
    await refreshFlows();
  } catch (error) { message(error.message); }
});

stepRow("action");

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
