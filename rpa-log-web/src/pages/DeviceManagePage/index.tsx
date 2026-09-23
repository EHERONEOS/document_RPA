import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
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
  PlatformQueueAssignment,
  assignQueue,
  createDevice,
  fetchDashboard,
  restartAllQueues,
  sendQueueCommand,
  unassignQueue,
} from '../../api/platform';

const STATE_COLORS: Record<string, string> = {
  RUNNING: 'green',
  PAUSED: 'gold',
  STOPPED: 'default',
  UNREPORTED: 'default',
};

/** 把设备列表按 deviceId 分组出各自的队列绑定 */
function groupByDevice(queues: PlatformQueueAssignment[]): Record<string, PlatformQueueAssignment[]> {
  return queues.reduce<Record<string, PlatformQueueAssignment[]>>((acc, item) => {
    (acc[item.deviceId] ??= []).push(item);
    return acc;
  }, {});
}

/** 设备管理页：新增设备（一次性注册令牌）+ 队列绑定/命令（平台维护 API） */
export default function DeviceManagePage() {
  const [dashboard, setDashboard] = useState<PlatformDashboard>({ devices: [], queues: [] });
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm<{ deviceId: string; displayName: string }>();
  const [bindTarget, setBindTarget] = useState<PlatformDevice | null>(null);
  const [bindForm] = Form.useForm<{ queueName: string }>();
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

  const submitBind = async () => {
    if (!bindTarget) return;
    const values = await bindForm.validateFields();
    try {
      await assignQueue(bindTarget.deviceId, values.queueName.trim());
      message.success(`已投递 assign 命令：${values.queueName.trim()}`);
      setBindTarget(null);
      bindForm.resetFields();
      await load();
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const runAction = async (action: () => Promise<unknown>, tip: string) => {
    try {
      await action();
      message.success(tip);
      await load();
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const grouped = groupByDevice(dashboard.queues);

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
      title: '队列绑定',
      key: 'queues',
      render: (_: unknown, record: PlatformDevice) => (grouped[record.deviceId]?.length ?? 0),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: unknown, record: PlatformDevice) => (
        <Space>
          <Button size="small" type="primary" ghost icon={<PlusCircleOutlined />} onClick={() => setBindTarget(record)}>
            分配队列
          </Button>
          <Popconfirm
            title="向该设备全部队列投递协作式重启？"
            onConfirm={() => void runAction(() => restartAllQueues(record.deviceId), 'restart_all 命令已投递')}
          >
            <Button size="small">全部重启</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const expandedRowRender = (record: PlatformDevice) => {
    const queues = grouped[record.deviceId] ?? [];
    return (
      <Table
        rowKey="queueName"
        size="small"
        pagination={false}
        dataSource={queues}
        columns={[
          { title: '队列', dataIndex: 'queueName', key: 'queueName' },
          {
            title: '期望/实际状态',
            key: 'state',
            render: (_: unknown, q: PlatformQueueAssignment) => (
              <Space>
                <Tag>{q.desiredState}</Tag>
                <Tag color={STATE_COLORS[q.state] ?? 'default'}>{q.state}</Tag>
              </Space>
            ),
          },
          {
            title: '操作',
            key: 'ops',
            width: 320,
            render: (_: unknown, q: PlatformQueueAssignment) => (
              <Space size={4}>
                <Button size="small" onClick={() => void runAction(() => sendQueueCommand(q.deviceId, q.queueName, 'pause'), 'pause 已投递')}>
                  暂停
                </Button>
                <Button size="small" onClick={() => void runAction(() => sendQueueCommand(q.deviceId, q.queueName, 'resume'), 'resume 已投递')}>
                  恢复
                </Button>
                <Button size="small" onClick={() => void runAction(() => sendQueueCommand(q.deviceId, q.queueName, 'restart'), 'restart 已投递')}>
                  重启
                </Button>
                <Popconfirm
                  title={`解除 ${q.queueName} 绑定？`}
                  onConfirm={() => void runAction(() => unassignQueue(q.deviceId, q.queueName), '已投递 unassign 并解绑')}
                >
                  <Button size="small" danger>
                    解除绑定
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
    );
  };

  return (
    <div>
      <PageHeader
        title="设备管理"
        description="新增设备并获取一次性注册令牌；为设备分配/解除队列，投递控制命令"
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
        <Table
          rowKey="deviceId"
          loading={loading}
          dataSource={dashboard.devices}
          columns={columns}
          pagination={false}
          expandable={{ expandedRowRender }}
        />
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
        title={`分配队列 → ${bindTarget?.deviceId ?? ''}`}
        open={bindTarget !== null}
        onOk={() => void submitBind()}
        onCancel={() => setBindTarget(null)}
        okText="分配"
        cancelText="取消"
      >
        <Form form={bindForm} layout="vertical">
          <Form.Item
            name="queueName"
            label="队列名"
            rules={[{ required: true, message: '请输入完整队列名' }]}
            extra="队列须已存在于 RabbitMQ（即 task 的 rpaTaskTopic），平台仅做设备绑定"
          >
            <Input placeholder="如 QTCT_ZIM_SI" />
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
