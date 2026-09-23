import { Alert, Button, Empty, Image, Modal, Typography } from 'antd';
import type { Execution } from '../../api/types';

interface FailReasonModalProps {
  execution: Execution | null;
  onClose: () => void;
}

/** 失败原因弹窗（§8.2，仅 FAILED）：红色 Alert 文案 + 失败截图可预览放大 */
export default function FailReasonModal({ execution, onClose }: FailReasonModalProps) {
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
          {execution.failImgUrl ? (
            <Image src={execution.failImgUrl} alt="失败截图" width="100%" />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无失败截图" />
          )}
        </>
      )}
    </Modal>
  );
}
