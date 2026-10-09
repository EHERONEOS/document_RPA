import axios from 'axios';

/**
 * 平台维护 API 客户端（设备管理/队列绑定，接口风格 {ok, error}，与日志 {code,data} 不同）。
 * 后台服务合并后同源 8766；dev 环境经 vite 代理。
 */

export interface PlatformDevice {
  deviceId: string;
  displayName: string;
  status: string;
  lastSeenAt: string | null;
  createdAt: string;
}

export interface PlatformQueueAssignment {
  deviceId: string;
  queueName: string;
  desiredState: string;
  assignmentVersion: number;
  state: string;
  pid: number | null;
  startedAt: string | null;
  stoppedAt: string | null;
  lastError: string;
}

export interface PlatformDashboard {
  devices: PlatformDevice[];
  queues: PlatformQueueAssignment[];
}

export interface CreateDeviceResult {
  ok: boolean;
  deviceId: string;
  enrollmentToken: string;
}

const platformHttp = axios.create({ baseURL: '/api', timeout: 15_000 });

platformHttp.interceptors.response.use(
  (response) => {
    const body = response.data as { ok?: boolean; error?: string };
    if (body && typeof body === 'object' && body.ok === false) {
      return Promise.reject(new Error(body.error || '操作失败'));
    }
    return response.data;
  },
  (error) => {
    const detail = error?.response?.data?.error;
    return Promise.reject(new Error(detail || error.message || '网络错误'));
  },
);

/** 设备与队列绑定总览 */
export async function fetchDashboard(): Promise<PlatformDashboard> {
  return platformHttp.get('/dashboard') as never;
}

/** 新增设备，返回一次性注册令牌 */
export async function createDevice(deviceId: string, displayName: string): Promise<CreateDeviceResult> {
  return platformHttp.post('/devices', { deviceId, displayName }) as never;
}

/** 删除设备（服务端级联清除绑定与命令，并通知 Agent 停止全部队列监听） */
export async function deleteDevice(deviceId: string): Promise<unknown> {
  return platformHttp.delete(`/devices/${encodeURIComponent(deviceId)}`) as never;
}

/** 修改设备 ID 与名称（ID 变更后机器侧需同步更新 QUEUE_CONTROL_DEVICE_ID 并重启） */
export async function updateDevice(
  deviceId: string,
  newDeviceId: string,
  displayName: string,
): Promise<unknown> {
  return platformHttp.put(`/devices/${encodeURIComponent(deviceId)}`, {
    deviceId: newDeviceId,
    displayName,
  }) as never;
}

/** 查看设备明文令牌（历史设备由 Agent 心跳自动回填明文，回填前返回 null） */
export async function fetchDeviceToken(
  deviceId: string,
): Promise<{ ok: boolean; deviceId: string; enrollmentToken: string | null }> {
  return platformHttp.get(`/devices/${encodeURIComponent(deviceId)}/token`) as never;
}

/** 分配队列到设备（服务端会投递 assign 命令） */
export async function assignQueue(deviceId: string, queueName: string): Promise<unknown> {
  return platformHttp.post(`/devices/${encodeURIComponent(deviceId)}/queues`, { queueName });
}

/** 解除设备的队列绑定 */
export async function unassignQueue(deviceId: string, queueName: string): Promise<unknown> {
  return platformHttp.delete(`/devices/${encodeURIComponent(deviceId)}/queues/${encodeURIComponent(queueName)}`);
}

/** 向设备单个队列投递 pause/resume/restart 命令 */
export async function sendQueueCommand(deviceId: string, queueName: string, action: string): Promise<unknown> {
  return platformHttp.post(`/devices/${encodeURIComponent(deviceId)}/queues/${encodeURIComponent(queueName)}/commands`, { action });
}

/** 向设备投递全部队列协作式重启命令 */
export async function restartAllQueues(deviceId: string): Promise<unknown> {
  return platformHttp.post(`/devices/${encodeURIComponent(deviceId)}/commands/restart-all`);
}
