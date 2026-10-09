import {
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  message,
} from 'antd';
import { PlusCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useMemo, useState } from 'react';
import PageHeader from '../../components/PageHeader';
import { formatDateTime } from '../../utils/format';
import {
  PlatformDashboard,
  PlatformQueueAssignment,
  assignQueue,
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

/** 队列状态 → 中文文案（对照 doc/队列状态维护架构说明.md §9） */
const STATE_TEXT: Record<string, string> = {
  RUNNING: '运行中',
  STARTING: '启动中',
  DRAINING: '排空中',
  RESTARTING: '重启中',
  PAUSED: '已暂停',
  STOPPED: '已停止',
  FAILED: '异常',
  UNREPORTED: '未上报',
  REMOVED: '已移除',
};

const stateText = (v: string) => STATE_TEXT[v] ?? v;

/** 队列管理页：为设备分配/解除队列、投递暂停/恢复/重启命令，并以平铺列表直接查看全部队列 */
export default function QueueManagePage() {
  const [dashboard, setDashboard] = useState<PlatformDashboard>({ devices: [], queues: [] });
  const [loading, setLoading] = useState(false);
  const [deviceFilter, setDeviceFilter] = useState<string | undefined>(undefined);
  const [addOpen, setAddOpen] = useState(false);
  const [addForm] = Form.useForm<{ deviceId: string; queueName: string }>();

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

  const rows = useMemo(
    () => (deviceFilter ? dashboard.queues.filter((q) => q.deviceId === deviceFilter) : dashboard.queues),
    [dashboard.queues, deviceFilter],
  );

  const runAction = async (action: () => Promise<unknown>, tip: string) => {
    try {
      await action();
      message.success(tip);
      await load();
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const submitAdd = async () => {
    const values = await addForm.validateFields();
    const queueName = values.queueName.trim();
    try {
      await assignQueue(values.deviceId, queueName);
      message.success(`已投递 assign 命令：${values.deviceId} ← ${queueName}`);
      setAddOpen(false);
      addForm.resetFields();
      setDeviceFilter(values.deviceId);
      await load();
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  const columns = [
    {
      title: '队列名',
      dataIndex: 'queueName',
      key: 'queueName',
      render: (v: string) => (
        <span className="mono" style={{ fontWeight: 200 }}>
          {v}
        </span>
      ),
    },
    { title: '所属设备', dataIndex: 'deviceId', key: 'deviceId', width: 300 },
    {
      title: '期望状态',
      dataIndex: 'desiredState',
      key: 'desiredState',
      width: 150,
      render: (v: string) => (
        <Tooltip title={v}>
          <Tag style={{ marginInlineEnd: 0 }}>{stateText(v)}</Tag>
        </Tooltip>
      ),
    },
    {
      title: '实际状态',
      dataIndex: 'state',
      key: 'state',
      width: 150,
      render: (v: string) => (
        <Tooltip title={v}>
          <Tag color={STATE_COLORS[v] ?? 'default'} style={{ marginInlineEnd: 0 }}>
            {stateText(v)}
          </Tag>
        </Tooltip>
      ),
    },
    {
      title: '进程 PID',
      dataIndex: 'pid',
      key: 'pid',
      width: 150,
      render: (v: number | null) => <span className="mono">{v ?? '—'}</span>,
    },
    {
      title: '启动时间',
      dataIndex: 'startedAt',
      key: 'startedAt',
      width: 240,
      render: (v: string | null) => <span className="mono">{formatDateTime(v)}</span>,
    },
    {
      title: '最近错误',
      dataIndex: 'lastError',
      key: 'lastError',
      ellipsis: { showTitle: false },
      render: (v: string) =>
        v ? (
          <Tooltip title={v} placement="topLeft">
            <span className="mono" style={{ color: 'rgba(0, 0, 0, 0.45)' }}>
              {v}
            </span>
          </Tooltip>
        ) : (
          '—'
        ),
    },
    {
      title: '操作',
      key: 'ops',
      width: 300,
      render: (_: unknown, q: PlatformQueueAssignment) => (
        <Space size={4}>
          <Popconfirm
            title={`立即停止 ${q.queueName} 正在执行的 RPA 任务并暂停？`}
            onConfirm={() => void runAction(() => sendQueueCommand(q.deviceId, q.queueName, 'pause'), 'pause 已投递')}
          >
            <Button size="small">暂停</Button>
          </Popconfirm>
          <Button
            size="small"
            onClick={() => void runAction(() => sendQueueCommand(q.deviceId, q.queueName, 'resume'), 'resume 已投递')}
          >
            恢复
          </Button>
          <Popconfirm
            title={`立即停止 ${q.queueName} 正在执行的 RPA 任务并重启？`}
            onConfirm={() => void runAction(() => sendQueueCommand(q.deviceId, q.queueName, 'restart'), 'restart 已投递')}
          >
            <Button size="small">重启</Button>
          </Popconfirm>
          <Popconfirm title={`解除 ${q.queueName} 绑定？`} onConfirm={() => void runAction(() => unassignQueue(q.deviceId, q.queueName), '已投递 unassign 并解绑')}>
            <Button size="small" danger>
              解除绑定
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="队列管理"
        description="为设备分配/解除队列并投递控制命令；单队列暂停/重启会立即停止正在执行的 RPA 任务"
      />
      <Card
        extra={
          <Space wrap>
            <Select
              allowClear
              placeholder="按设备筛选"
              style={{ minWidth: 160 }}
              value={deviceFilter}
              onChange={(v) => setDeviceFilter(v)}
              options={dashboard.devices.map((d) => ({ value: d.deviceId, label: `${d.deviceId}（${d.displayName}）` }))}
            />
            <Popconfirm
              title={deviceFilter ? `向 ${deviceFilter} 全部队列投递协作式重启？` : '请先在左侧选择一台设备'}
              onConfirm={() => deviceFilter && void runAction(() => restartAllQueues(deviceFilter), 'restart_all 命令已投递')}
              disabled={!deviceFilter}
            >
              <Button disabled={!deviceFilter}>全部重启</Button>
            </Popconfirm>
            <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusCircleOutlined />} onClick={() => setAddOpen(true)}>
              添加队列
            </Button>
          </Space>
        }
      >
        <Table
          rowKey={(q) => `${q.deviceId}::${q.queueName}`}
          loading={loading}
          dataSource={rows}
          columns={columns}
          pagination={rows.length > 10 ? { pageSize: 10, showTotal: (t) => `共 ${t} 条` } : false}
          locale={{
            emptyText: (
              <Empty description={deviceFilter ? '该设备暂无绑定队列' : '暂无队列，点击右上角「添加队列」为设备分配'} />
            ),
          }}
        />
      </Card>

      <Modal
        title="添加队列"
        open={addOpen}
        onOk={() => void submitAdd()}
        onCancel={() => setAddOpen(false)}
        okText="分配"
        cancelText="取消"
      >
        <Form form={addForm} layout="vertical">
          <Form.Item
            name="deviceId"
            label="目标设备"
            rules={[{ required: true, message: '请选择设备' }]}
            extra={dashboard.devices.length === 0 ? '暂无设备，请先在「设备管理」中新增' : undefined}
          >
            <Select
              placeholder="选择设备"
              disabled={dashboard.devices.length === 0}
              options={dashboard.devices.map((d) => ({ value: d.deviceId, label: `${d.deviceId}（${d.displayName}）` }))}
            />
          </Form.Item>
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
    </div>
  );
}
