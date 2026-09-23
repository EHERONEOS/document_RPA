import { Button, Empty, Image, Modal, Spin, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { fetchExecutionDetail } from '../../api/executions';
import type { ExecutionFile } from '../../api/types';
import StorageBadge from '../../components/StorageBadge';
import { formatFileSize } from '../../utils/format';

const TYPE_NAMES: Record<string, string> = {
  SCREEN_RECORDING_FILE: '屏幕录制',
  SUBMIT_RESULT_SCREENSHOT: '提交结果截图',
  SI_DRAFT_SCREENSHOT: 'SI 草稿截图',
  VGM_RESULT_SCREENSHOT: 'VGM 申报结果',
};

interface RecordFilesModalProps {
  executionId: number | null;
  onClose: () => void;
}

/**
 * 记录文件弹窗（§8.2，SUCCESS/FAILED 终态）：
 * 按 type 分组；图片 Image.PreviewGroup 缩略图；视频 <video controls>；
 * 每个文件带 OSS/LAN 存储角标；无文件显示 Empty。
 */
export default function RecordFilesModal({ executionId, onClose }: RecordFilesModalProps) {
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [files, setFiles] = useState<ExecutionFile[]>([]);

  useEffect(() => {
    if (executionId == null) {
      setFiles([]);
      setLoadError(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(false);
    fetchExecutionDetail(executionId)
      .then((data) => {
        if (!cancelled) setFiles(data.files);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [executionId]);

  // 按 type 分组（保持服务端返回顺序）
  const groups = useMemo(() => {
    const map = new Map<string, ExecutionFile[]>();
    files.forEach((file) => {
      const bucket = map.get(file.type);
      if (bucket) bucket.push(file);
      else map.set(file.type, [file]);
    });
    return Array.from(map.entries());
  }, [files]);

  return (
    <Modal
      open={executionId != null}
      title="记录文件"
      width={760}
      onCancel={onClose}
      footer={
        <Button type="primary" onClick={onClose}>
          关 闭
        </Button>
      }
    >
      <Spin spinning={loading}>
        {loadError ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="记录文件加载失败" />
        ) : groups.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无记录文件" />
        ) : (
          groups.map(([type, groupFiles]) => (
            <div key={type} style={{ marginBottom: 20 }}>
              <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 12 }}>
                {TYPE_NAMES[type] ?? type}
                <span
                  style={{
                    color: 'rgba(0, 0, 0, 0.45)',
                    fontWeight: 400,
                    fontSize: 12,
                    marginLeft: 8,
                  }}
                >
                  （{groupFiles.length} 个文件）
                </span>
              </Typography.Title>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                  gap: 12,
                }}
              >
                <Image.PreviewGroup>
                  {groupFiles.map((file) => (
                    <div
                      key={file.fileId}
                      style={{ border: '1px solid #f0f0f0', borderRadius: 8, overflow: 'hidden' }}
                    >
                      {file.mediaType === 'VIDEO' ? (
                        <video
                          controls
                          preload="metadata"
                          src={file.url}
                          style={{ width: '100%', display: 'block', background: '#000', aspectRatio: '16 / 9' }}
                        />
                      ) : (
                        <Image
                          src={file.url}
                          alt={file.fileName}
                          width="100%"
                          height={150}
                          style={{ objectFit: 'cover' }}
                        />
                      )}
                      <div
                        style={{
                          padding: '8px 12px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          fontSize: 12,
                          color: 'rgba(0, 0, 0, 0.65)',
                        }}
                      >
                        <span
                          title={file.fileName}
                          style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        >
                          {file.fileName}
                        </span>
                        <StorageBadge storage={file.storage} />
                        <span style={{ flex: 'none', color: 'rgba(0, 0, 0, 0.45)' }}>
                          {formatFileSize(file.fileSize)}
                        </span>
                      </div>
                    </div>
                  ))}
                </Image.PreviewGroup>
              </div>
            </div>
          ))
        )}
      </Spin>
    </Modal>
  );
}
