import { Tag } from 'antd';
import type { ExecutionStatus } from '../../api/types';
import { STATUS_TEXT } from '../../utils/format';

interface StatusMeta {
  color: 'success' | 'error' | 'warning';
  running?: boolean;
}

/** 状态 → Tag 映射（§8.2/§9.4）：成功=绿 失败=红 超时=红 运行中=黄+圆点动画 */
const STATUS_META: Record<ExecutionStatus, StatusMeta> = {
  SUCCESS: { color: 'success' },
  FAILED: { color: 'error' },
  TIMEOUT: { color: 'error' },
  RUNNING: { color: 'warning', running: true },
};

/** 执行状态标签 */
export default function StatusTag({ status }: { status: ExecutionStatus }) {
  const meta = STATUS_META[status];
  return (
    <Tag color={meta.color} style={{ marginInlineEnd: 0 }}>
      {meta.running && <span className="running-dot" />}
      {STATUS_TEXT[status]}
    </Tag>
  );
}
