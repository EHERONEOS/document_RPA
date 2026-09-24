import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { PlusCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import {
  PlatformDashboard,
  PlatformDevice,
  createDevice,
  fetchDashboard,
} from '../../api/platform';

/** 统计某设备绑定队列中处于运行态的数量 */
function runningCount(queues: PlatformDashboard['queues'], deviceId: string): number {
  return queues.filter((q) => q.deviceId === deviceId && q.state === 'RUNNING').length;
}

/** 设备管理页：仅负责设备配置（新增设备 + 一次性注册令牌）与设备运行状态查看；队列相关操作见「队列管理」页 */
export default function DeviceManagePage() {
  const [dashboard, setDashboard] = useState<PlatformDashboard>({ devices: [], queues: [] });
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm<{ deviceId: string; displayName: string }>();
  const [enrolled, setEnrolled] = useState<{ deviceId: string; enrollmentToken: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDashboard(await fetchDashboard());
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const submitCreate = async () => {
    const values = await form.validateFields();
    try {
      const result = await createDevice(values.deviceId.trim(), values.displayName.trim());
      setCreateOpen(false);
      form.resetFields();
      setEnrolled({ deviceId: result.deviceId, enrollmentToken: result.enrollmentToken });
      await load();
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const columns = [
    { title: '设备 ID', dataIndex: 'deviceId', key: 'deviceId' },
    { title: '名称', dataIndex: 'displayName', key: 'displayName' },
    {
      title: '在线状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'ONLINE' ? 'green' : 'default'}>{status === 'ONLINE' ? '在线' : '离线'}</Tag>
      ),
    },
    { title: '最近心跳', dataIndex: 'lastSeenAt', key: 'lastSeenAt', render: (v: string | null) => v ?? '—' },
    {
      title: '绑定队列数',
      key: 'queueCount',
      width: 110,
      render: (_: unknown, record: PlatformDevice) =>
        dashboard.queues.filter((q) => q.deviceId === record.deviceId).length,
    },
    {
      title: '队列运行状态',
      key: 'queueRunning',
      width: 130,
      render: (_: unknown, record: PlatformDevice) => {
        const bound = dashboard.queues.filter((q) => q.deviceId === record.deviceId).length;
        const running = runningCount(dashboard.queues, record.deviceId);
        return (
          <Tag color={bound === 0 ? 'default' : running > 0 ? 'green' : 'gold'} style={{ marginInlineEnd: 0 }}>
            {running}/{bound} 运行中
          </Tag>
        );
      },
    },
  ];

  return (
    <div>
      <PageHeader
        title="设备管理"
        description="新增设备并获取一次性注册令牌，查看设备在线与队列运行状态；队列的分配与控制请前往「队列管理」"
      />
      <Card
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusCircleOutlined />} onClick={() => setCreateOpen(true)}>
              新增设备
            </Button>
          </Space>
        }
      >
        <Table rowKey="deviceId" loading={loading} dataSource={dashboard.devices} columns={columns} pagination={false} />
      </Card>

      <Modal
        title="新增设备"
        open={createOpen}
        onOk={() => void submitCreate()}
        onCancel={() => setCreateOpen(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="deviceId"
            label="设备 ID"
            rules={[{ required: true, message: '请输入设备 ID' }]}
            extra="全局唯一，创建后不可修改"
          >
            <Input placeholder="如 DEVICE_2" />
          </Form.Item>
          <Form.Item name="displayName" label="设备名称" rules={[{ required: true, message: '请输入设备名称' }]}>
            <Input placeholder="如 2 号机" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="设备创建成功"
        open={enrolled !== null}
        onOk={() => setEnrolled(null)}
        onCancel={() => setEnrolled(null)}
        okText="我已保存"
        cancelText="关闭"
      >
        <Alert type="warning" showIcon message="一次性注册令牌，关闭后不再显示，请立即复制保存" style={{ marginBottom: 12 }} />
        <Typography.Paragraph copyable style={{ marginBottom: 4 }}>
          设备 ID：{enrolled?.deviceId}
        </Typography.Paragraph>
        <Typography.Paragraph code copyable style={{ marginBottom: 0 }}>
          {enrolled?.enrollmentToken}
        </Typography.Paragraph>
      </Modal>
    </div>
  );
}
