/** 执行状态（§4.1）：运行中 / 成功 / 失败 / 超时 */
export type ExecutionStatus = 'RUNNING' | 'SUCCESS' | 'FAILED' | 'TIMEOUT';

/** 日志级别（§6.2）：INFO / WARN / ERROR / SUCCESS 四级 */
export type LogLevel = 'INFO' | 'WARN' | 'ERROR' | 'SUCCESS';

/** 文件媒体类型（§4.3） */
export type FileMediaType = 'VIDEO' | 'IMAGE';

/** 文件存储来源（§7）：OSS / 局域网 */
export type FileStorage = 'OSS' | 'LAN';

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

/** 通用分页包装 */
export interface PageResult<T> {
  total: number;
  page: number;
  pageSize: number;
  list: T[];
}

/** 设备行（§4.4 /devices） */
export interface DeviceInfo {
  deviceName: string;
  osInfo: string;
  boundQueueCount: number;
  todayCount: number;
  successRate: number | null;
  lastSeenAt: string | null;
  online: boolean;
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
