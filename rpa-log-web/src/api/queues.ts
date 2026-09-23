import http from './http';
import type { QueueInfo } from './types';

/** GET /api/v1/queues —— 队列列表 + 统计（今日执行、成功率、平均耗时） */
export function fetchQueues(): Promise<QueueInfo[]> {
  return http.get<never, QueueInfo[]>('/queues');
}
