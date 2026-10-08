/** 执行状态（§4.1）：运行中 / 成功 / 失败 / 超时 / 已废弃 */
export type ExecutionStatus = 'RUNNING' | 'SUCCESS' | 'FAILED' | 'TIMEOUT' | 'DEPRECATED';

/** 日志级别（§6.2）：INFO / WARN / ERROR / SUCCESS 四级 */
export type LogLevel = 'INFO' | 'WARN' | 'ERROR' | 'SUCCESS';

/** 文件媒体类型（§4.3） */
export type FileMediaType = 'VIDEO' | 'IMAGE';

/** 文件存储来源（§7 / §9）：OSS / 局域网 / 本地保留（视频 OSS 失败） */
export type FileStorage = 'OSS' | 'LAN' | 'LOCAL';

/** 执行记录主表行（§4.1，列表页数据源） */
export interface Execution {
  executionId: number;
  rpaMessageId: string;
  jobId: string;
  queueName: string;
  deviceName: string;
  taskId: string | null;
  customerCode: string | null;
  carrierCode: string | null;
  businessCode: string | null;
  status: ExecutionStatus;
  remark: string | null;
  failImgUrl: string | null;
  logCount: number;
  startedAt: string;
  finishedAt: string | null;
  durationSeconds: number | null;
  createTime: string;
}

/** 执行日志明细行（§4.2，抽屉数据源，服务端按 seq DESC 返回） */
export interface ExecutionLog {
  seq: number;
  level: LogLevel;
  message: string;
  sourceFile: string | null;
  sourceLine: number | null;
  logTime: string;
}

/** 记录文件（§4.3，记录文件弹窗数据源） */
export interface ExecutionFile {
  fileId: number;
  type: string;
  mediaType: FileMediaType;
  fileName: string;
  url: string;
  objectName?: string;
  remark?: string;
  storage: FileStorage;
  fileSize: number | null;
  createTime: string;
}

/** 执行详情：主记录 + 日志明细 + 文件列表（§5.2） */
export interface ExecutionDetail {
  execution: Execution;
  logs: ExecutionLog[];
  files: ExecutionFile[];
}

/** 删除执行记录结果：包含实际级联清理的数据量 */
export interface DeleteExecutionsResult {
  requested: number;
  deleted: number;
  deletedLogCount: number;
  deletedFileCount: number;
}

/** 通用分页包装 */
export interface PageResult<T> {
  total: number;
  page: number;
  pageSize: number;
  list: T[];
}

/** 队列行（§4.4 /queues） */
export interface QueueInfo {
  queueName: string;
  customerCode: string;
  carrierCode: string;
  businessCode: string;
  todayCount: number;
  successRate: number | null;
  avgDurationSeconds: number | null;
}

/** 首页统计卡（§5.2 /stats/summary） */
export interface StatsSummary {
  todayTotal: number;
  successCount: number;
  failedCount: number;
  runningCount: number;
}
