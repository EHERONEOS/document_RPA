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
import { DeleteOutlined, EditOutlined, KeyOutlined, PlusCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import { formatDateTime } from '../../utils/format';
import {
  PlatformDashboard,
  PlatformDevice,
  createDevice,
  deleteDevice,
  fetchDashboard,
  fetchDeviceToken,
  updateDevice,
} from '../../api/platform';

/** 统计某设备绑定队列中处于运行态的数量 */
function runningCount(queues: PlatformDashboard['queues'], deviceId: string): number {
  return queues.filter((q) => q.deviceId === deviceId && q.state === 'RUNNING').length;
}

/** 设备管理页：负责设备配置（新增/编辑/删除、注册令牌查看与重置）与设备运行状态查看；队列相关操作见「队列管理」页 */
export default function DeviceManagePage() {
  const [dashboard, setDashboard] = useState<PlatformDashboard>({ devices: [], queues: [] });
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm<{ deviceId: string; displayName: string }>();
  const [enrolled, setEnrolled] = useState<{ deviceId: string; enrollmentToken: string } | null>(null);
  const [editing, setEditing] = useState<PlatformDevice | null>(null);
  const [editForm] = Form.useForm<{ deviceId: string; displayName: string }>();
  const [tokenView, setTokenView] = useState<{ deviceId: string; token: string | null } | null>(null);
  const [tokenLoading, setTokenLoading] = useState(false);

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

  const submitDelete = async (record: PlatformDevice) => {
    try {
      await deleteDevice(record.deviceId);
      message.success(`设备 ${record.deviceId} 已删除`);
      await load();
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const openEdit = (record: PlatformDevice) => {
    setEditing(record);
    editForm.setFieldsValue({ deviceId: record.deviceId, displayName: record.displayName });
  };

  const submitEdit = async () => {
    if (!editing) return;
    const values = await editForm.validateFields();
    try {
      await updateDevice(editing.deviceId, values.deviceId.trim(), values.displayName.trim());
      setEditing(null);
      if (values.deviceId.trim().toUpperCase() !== editing.deviceId) {
        message.warning('设备 ID 已变更，请同步更新机器侧 QUEUE_CONTROL_DEVICE_ID 并重启 Agent');
      } else {
        message.success('设备信息已更新');
      }
      await load();
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const openToken = async (record: PlatformDevice) => {
    setTokenLoading(true);
    setTokenView({ deviceId: record.deviceId, token: null });
    try {
      const result = await fetchDeviceToken(record.deviceId);
      setTokenView({ deviceId: result.deviceId, token: result.enrollmentToken });
    } catch (error) {
      setTokenView(null);
      message.error((error as Error).message);
    } finally {
      setTokenLoading(false);
    }
  };

  const columns = [
    { title: '设备 ID', dataIndex: 'deviceId', key: 'deviceId', width: 300 },
    { title: '名称', dataIndex: 'displayName', key: 'displayName' },
    {
      title: '在线状态',
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (status: string) => (
        <Tag color={status === 'ONLINE' ? 'green' : 'default'}>{status === 'ONLINE' ? '在线' : '离线'}</Tag>
      ),
    },
    {
      title: '最近心跳',
      dataIndex: 'lastSeenAt',
      key: 'lastSeenAt',
      width: 240,
      render: (v: string | null) => <span className="mono">{formatDateTime(v)}</span>,
    },
    {
      title: '绑定队列数',
      key: 'queueCount',
      width: 150,
      render: (_: unknown, record: PlatformDevice) =>
        dashboard.queues.filter((q) => q.deviceId === record.deviceId).length,
    },
    {
      title: '队列运行状态',
      key: 'queueRunning',
      width: 150,
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
    {
      title: '操作',
      key: 'actions',
      width: 250,
      render: (_: unknown, record: PlatformDevice) => {
        const bound = dashboard.queues.filter((q) => q.deviceId === record.deviceId).length;
        return (
          <Space>
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
              编辑
            </Button>
            <Button
              type="link"
              size="small"
              icon={<KeyOutlined />}
              onClick={() => void openToken(record)}
            >
              查看令牌
            </Button>
            <Popconfirm
              title={`删除设备 ${record.deviceId}？`}
              description={
                bound > 0
                  ? `该设备仍绑定 ${bound} 个队列，删除后将解除全部绑定并通知其 Agent 停止监听`
                  : '删除后将清除注册令牌与历史命令，Agent 无法再上报'
              }
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => void submitDelete(record)}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <PageHeader
        title="设备管理"
        description="支持新增、编辑（ID/名称）与删除设备，点击「查看令牌」可随时查看注册令牌；队列的分配与控制请前往「队列管理」"
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
            extra="全局唯一，创建后可在「编辑」中修改"
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
        <Alert type="info" showIcon message="注册令牌已保存，后续可随时点击设备列表中的「查看令牌」查看" style={{ marginBottom: 12 }} />
        <Typography.Paragraph copyable style={{ marginBottom: 4 }}>
          设备 ID：{enrolled?.deviceId}
        </Typography.Paragraph>
        <Typography.Paragraph code copyable style={{ marginBottom: 0 }}>
          {enrolled?.enrollmentToken}
        </Typography.Paragraph>
      </Modal>

      <Modal
        title={`编辑设备：${editing?.deviceId ?? ''}`}
        open={editing !== null}
        onOk={() => void submitEdit()}
        onCancel={() => setEditing(null)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="deviceId"
            label="设备 ID"
            rules={[{ required: true, message: '请输入设备 ID' }]}
            extra="修改后机器侧 Agent 需同步更新 QUEUE_CONTROL_DEVICE_ID 并重启；注册令牌与队列绑定保持不变"
          >
            <Input placeholder="如 DEVICE_2" />
          </Form.Item>
          <Form.Item name="displayName" label="设备名称" rules={[{ required: true, message: '请输入设备名称' }]}>
            <Input placeholder="如 2 号机" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="查看设备令牌"
        open={tokenView !== null}
        onCancel={() => setTokenView(null)}
        footer={[
          <Button key="close" type="primary" onClick={() => setTokenView(null)}>
            关闭
          </Button>,
        ]}
      >
        <Typography.Paragraph copyable style={{ marginBottom: 8 }}>
          设备：{tokenView?.deviceId}
        </Typography.Paragraph>
        {tokenLoading ? (
          <Typography.Paragraph type="secondary">正在加载令牌…</Typography.Paragraph>
        ) : tokenView?.token ? (
          <Typography.Paragraph code copyable style={{ marginBottom: 0 }}>
            {tokenView.token}
          </Typography.Paragraph>
        ) : (
          <Alert
            type="warning"
            showIcon
            message="该设备的令牌明文尚未补齐"
            description="该设备创建于令牌查看功能启用前，其 Agent 下一次心跳上报后会自动补齐明文（约 15 秒）；若设备已不再上线，可在机器侧 .env 的 QUEUE_CONTROL_DEVICE_TOKEN 中查看原令牌。"
          />
        )}
      </Modal>
    </div>
  );
}
