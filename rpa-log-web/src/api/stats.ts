import http from './http';
import type { StatsSummary } from './types';

/** GET /api/v1/stats/summary —— 首页统计卡（今日总数/成功/失败/运行中） */
export function fetchStatsSummary(): Promise<StatsSummary> {
  return http.get<never, StatsSummary>('/stats/summary');
}
