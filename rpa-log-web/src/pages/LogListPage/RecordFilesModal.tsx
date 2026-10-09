import { Alert, Button, Empty, Image, Modal, Spin, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { fetchExecutionFiles, fetchOssFileUrl } from '../../api/executions';
import type { ExecutionFile } from '../../api/types';
import StorageBadge from '../../components/StorageBadge';
import { formatFileSize } from '../../utils/format';
import './loglist.css';

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

interface PreviewFile extends ExecutionFile {
  previewUrl: string;
  previewError: string;
}

/**
 * 记录文件弹窗（§8.2 / §9）：
 * 按 type 分组；图片 Image.PreviewGroup 缩略图；视频 <video controls>；
 * OSS 视频/截图均用 objectName 换临时地址（截图与录屏同方案）；
 * LOCAL 展示失败信息与本地路径。
 * 截图放大预览宽度固定为屏幕 60%（见 loglist.css .record-file-preview）。
 */
export default function RecordFilesModal({ executionId, onClose }: RecordFilesModalProps) {
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [files, setFiles] = useState<PreviewFile[]>([]);

  useEffect(() => {
    if (executionId == null) {
      setFiles([]);
      setLoadError(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(false);
    fetchExecutionFiles(executionId)
      .then(async (files) => {
        const resolved = await Promise.all(files.map(resolvePreview));
        if (!cancelled) setFiles(resolved);
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
    const map = new Map<string, PreviewFile[]>();
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
                  gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))',
                  gap: 12,
                }}
              >
                <Image.PreviewGroup preview={{ rootClassName: 'record-file-preview' }}>
                  {groupFiles.map((file) => (
                    <div
                      key={file.fileId}
                      style={{ border: '1px solid #f0f0f0', borderRadius: 8, overflow: 'hidden' }}
                    >
                      <FilePreview file={file} />
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

function FilePreview({ file }: { file: PreviewFile }) {
  if (file.storage === 'LOCAL' || (!file.previewUrl && file.remark)) {
    return (
      <Alert
        type="warning"
        showIcon
        message={file.remark || '视频保留在本地，无在线地址'}
        style={{ margin: 12 }}
      />
    );
  }
  if (file.previewError) {
    return <Alert type="error" showIcon message={file.previewError} style={{ margin: 12 }} />;
  }
  if (!file.previewUrl) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无可预览地址" style={{ margin: 12 }} />;
  }
  if (file.mediaType === 'VIDEO') {
    return (
      <video
        controls
        preload="metadata"
        src={file.previewUrl}
        style={{ width: '100%', display: 'block', background: '#000', aspectRatio: '16 / 9' }}
      />
    );
  }
  return (
    <Image
      src={file.previewUrl}
      alt={file.fileName}
      width="100%"
      height={150}
      style={{ objectFit: 'cover' }}
    />
  );
}

async function resolvePreview(file: ExecutionFile): Promise<PreviewFile> {
  if (file.storage === 'LOCAL') {
    return { ...file, previewUrl: '', previewError: '' };
  }
  // 新记录（录屏/截图）只存 objectName：优先换临时地址；
  // 存量记录回退 url 完整地址（LAN 文件或旧版 OSS 直存）。
  if (file.objectName) {
    try {
      return { ...file, previewUrl: await fetchOssFileUrl(file.objectName), previewError: '' };
    } catch {
      return { ...file, previewUrl: '', previewError: `换取临时地址失败：${file.objectName}` };
    }
  }
  if (file.url) {
    return { ...file, previewUrl: file.url, previewError: '' };
  }
  return { ...file, previewUrl: '', previewError: file.remark || '' };
}
