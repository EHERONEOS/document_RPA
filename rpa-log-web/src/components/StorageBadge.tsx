import { Tag } from 'antd';
import type { FileStorage } from '../api/types';

/** OSS/LAN 存储角标（§8.2 记录文件弹窗：每个文件标注存储来源） */
export default function StorageBadge({ storage }: { storage: FileStorage | string }) {
  const isLan = storage === 'LAN';
  return (
    <Tag
      color={isLan ? 'gold' : 'geekblue'}
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
