import type { ExecutionStatus, LogLevel } from '../api/types';

/** 日志级别 → 文本色（§9.4：灰 / 绿 / 黄 / 红） */
export const LOG_LEVEL_COLORS: Record<LogLevel, string> = {
  INFO: 'rgba(0, 0, 0, 0.45)',
  SUCCESS: '#52c41a',
  WARN: '#faad14',
  ERROR: '#ff4d4f',
};

/** 执行状态 → 中文文案（§8.2） */
export const STATUS_TEXT: Record<ExecutionStatus, string> = {
  RUNNING: '运行中',
  SUCCESS: '成功',
  FAILED: '失败',
  TIMEOUT: '超时',
};

const FINAL_STATUSES: readonly ExecutionStatus[] = ['SUCCESS', 'FAILED', 'TIMEOUT'];

/** 是否终态（成功/失败/超时）：终态才展示结束时间与耗时 */
export function isFinalStatus(status: ExecutionStatus): boolean {
  return FINAL_STATUSES.includes(status);
}

/**
 * durationSeconds → "2m 38s" 样式；
 * 1 小时以上 "1h 02m 05s"，1 分钟内 "38s"，空值显示 "—"（§8.2）
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '—';
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return hours > 0 ? `${hours}h ${pad(minutes)}m ${pad(secs)}s` : `${minutes}m ${pad(secs)}s`;
}

/** 成功率（百分制 1 位小数）→ "88.2%"，空值显示 "—" */
export function formatRate(rate: number | null | undefined): string {
  if (rate === null || rate === undefined || Number.isNaN(rate)) return '—';
  return `${rate}%`;
}

/** 文件字节数 → "8.6 MB" 样式，空值/0 显示 "—" */
export function formatFileSize(size: number | null | undefined): string {
  if (size === null || size === undefined || size <= 0) return '—';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}
