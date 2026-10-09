import { Alert, Button, Empty, Image, Modal, Spin, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { fetchOssFileUrl } from '../../api/executions';
import type { Execution } from '../../api/types';

interface FailReasonModalProps {
  execution: Execution | null;
  onClose: () => void;
}

interface FailImageState {
  loading: boolean;
  url: string;
  error: string;
}

/** 失败截图地址解析：优先 objectName 换临时地址（同录屏方案）；存量记录回退 failImgUrl 完整地址。 */
function useFailImageUrl(execution: Execution | null): FailImageState {
  const [state, setState] = useState<FailImageState>({ loading: false, url: '', error: '' });

  useEffect(() => {
    if (!execution) {
      setState({ loading: false, url: '', error: '' });
      return;
    }
    const objectName = execution.failImgObjectName || '';
    if (!objectName) {
      setState({ loading: false, url: execution.failImgUrl || '', error: '' });
      return;
    }
    let cancelled = false;
    setState({ loading: true, url: '', error: '' });
    fetchOssFileUrl(objectName)
      .then((url) => {
        if (!cancelled) setState({ loading: false, url, error: '' });
      })
      .catch(() => {
        if (!cancelled) setState({ loading: false, url: '', error: `换取临时地址失败：${objectName}` });
      });
    return () => {
      cancelled = true;
    };
  }, [execution]);

  return state;
}

/** 失败原因弹窗（§8.2，仅 FAILED）：红色 Alert 文案 + 失败截图可预览放大 */
export default function FailReasonModal({ execution, onClose }: FailReasonModalProps) {
  const failImage = useFailImageUrl(execution);

  return (
    <Modal
      open={execution != null}
      title={<span style={{ color: '#ff4d4f' }}>失败原因</span>}
      width={680}
      onCancel={onClose}
      footer={
        <Button type="primary" onClick={onClose}>
          关 闭
        </Button>
      }
    >
      {execution && (
        <>
          <Alert
            type="error"
            showIcon
            message={execution.remark || '（服务端未返回失败原因文案）'}
            style={{ marginBottom: 16 }}
          />
          <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 8 }}>
            失败截图
          </Typography.Title>
          {failImage.loading ? (
            <div style={{ padding: '24px 0', textAlign: 'center', color: 'rgba(0, 0, 0, 0.45)' }}>
              <Spin />
              <div style={{ marginTop: 8 }}>正在换取截图临时地址...</div>
            </div>
          ) : failImage.error ? (
            <Alert type="error" showIcon message={failImage.error} />
          ) : failImage.url ? (
            <Image src={failImage.url} alt="失败截图" width="100%" />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无失败截图" />
          )}
        </>
      )}
    </Modal>
  );
}
