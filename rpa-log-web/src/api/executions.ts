import http from './http';
import type { DeleteExecutionsResult, Execution, ExecutionDetail, ExecutionFile, ExecutionStatus, PageResult } from './types';

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

/** GET /api/v1/execution/detail —— 主记录 + 日志明细（seq DESC） */
export function fetchExecutionDetail(executionId: number): Promise<ExecutionDetail> {
  return http.get<never, ExecutionDetail>('/execution/detail', { params: { executionId } });
}

/** GET /api/v1/execution/files —— 记录文件列表（与详情拆分，记录文件弹窗按需加载） */
export function fetchExecutionFiles(executionId: number): Promise<ExecutionFile[]> {
  return http.get<never, ExecutionFile[]>('/execution/files', { params: { executionId } });
}

/** 经日志服务代理：用 OSS objectName 换带签名的临时访问地址（设计文档 §9） */
export async function fetchOssFileUrl(objectName: string): Promise<string> {
  const data = await http.get<never, { url?: string }>('/files/oss-url', { params: { objectName } });
  const url = data?.url || '';
  if (!url) {
    throw new Error(`未拿到 objectName=${objectName} 的临时地址`);
  }
  return url;
}

/** POST /api/v1/executions/delete —— 批量删除执行记录，并级联删除关联日志与文件 */
export function deleteExecutions(executionIds: number[]): Promise<DeleteExecutionsResult> {
  return http.post<never, DeleteExecutionsResult>('/executions/delete', { executionIds });
}
