import { Tag } from 'antd';
import type { FileStorage } from '../api/types';

/** OSS/LAN/LOCAL 存储角标（§8.2 记录文件弹窗：每个文件标注存储来源） */
const STORAGE_COLOR: Record<string, string> = {
  LAN: 'gold',
  LOCAL: 'default',
  OSS: 'geekblue',
};

export default function StorageBadge({ storage }: { storage: FileStorage | string }) {
  return (
    <Tag
      color={STORAGE_COLOR[storage] ?? 'geekblue'}
      style={{
        marginInlineEnd: 0,
        flex: 'none',
        fontSize: 11,
        lineHeight: '18px',
        padding: '0 5px',
        borderRadius: 4,
      }}
    >
      {storage}
    </Tag>
  );
}
