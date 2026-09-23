import { Tooltip } from 'antd';
import type { LogLevel } from '../api/types';
import { LOG_LEVEL_COLORS } from '../utils/format';

interface LogLevelTextProps {
  level: LogLevel;
  message: string;
}

/**
 * 日志内容文本（§8.2/§9.4）：按级别着色，单行省略号，
 * 悬浮 Tooltip 展示完整内容（截断由外层容器负责）。
 */
export default function LogLevelText({ level, message }: LogLevelTextProps) {
  return (
    <Tooltip title={message} placement="topLeft" mouseEnterDelay={0.3}>
      <span style={{ color: LOG_LEVEL_COLORS[level] ?? 'rgba(0, 0, 0, 0.88)' }}>{message}</span>
    </Tooltip>
  );
}
