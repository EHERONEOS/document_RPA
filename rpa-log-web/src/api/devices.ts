import http from './http';
import type { DeviceInfo } from './types';

/** GET /api/v1/devices —— 设备列表 + 统计（今日执行、成功率、最近心跳） */
export function fetchDevices(): Promise<DeviceInfo[]> {
  return http.get<never, DeviceInfo[]>('/devices');
}
