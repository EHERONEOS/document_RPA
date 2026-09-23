import http from './http';
import type { Execution, ExecutionDetail, ExecutionStatus, PageResult } from './types';

/** 列表查询条件（§5.2：rpaMessageId/jobId 后缀模糊，queueName/deviceName/status 精确） */
export interface ExecutionQuery {
  page: number;
  pageSize: number;
  rpaMessageId?: string;
  jobId?: string;
  queueName?: string;
  deviceName?: string;
  status?: ExecutionStatus;
}

/** GET /api/v1/executions —— 执行记录分页列表 */
export function fetchExecutions(params: ExecutionQuery): Promise<PageResult<Execution>> {
  return http.get<never, PageResult<Execution>>('/executions', { params });
}

/** GET /api/v1/execution/detail —— 主记录 + 日志明细（seq DESC）+ 文件列表 */
export function fetchExecutionDetail(executionId: number): Promise<ExecutionDetail> {
  return http.get<never, ExecutionDetail>('/execution/detail', { params: { executionId } });
}
