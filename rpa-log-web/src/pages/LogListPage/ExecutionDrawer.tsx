import { ReloadOutlined } from '@ant-design/icons';
import { Button, Descriptions, Drawer, Space, Spin, Table, Typography } from 'antd';
import type { DescriptionsProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchExecutionDetail } from '../../api/executions';
import type { ExecutionDetail, ExecutionLog } from '../../api/types';
import LogLevelText from '../../components/LogLevelText';
import { formatDuration, isFinalStatus } from '../../utils/format';
import StatusTag from './StatusTag';

interface ExecutionDrawerProps {
  executionId: number | null;
  onClose: () => void;
  /** 每次拉到最新详情后回调父级（用于静默刷新列表统计） */
  onUpdated?: () => void;
}

const POLL_INTERVAL_MS = 30_000;

/** 视口高度 → 日志区滚动高度（抽屉头部+Descriptions 约占 offset 像素） */
function useViewportLogHeight(offset: number): number {
  const [height, setHeight] = useState(() => Math.max(240, window.innerHeight - offset));
  useEffect(() => {
    const handleResize = () => setHeight(Math.max(240, window.innerHeight - offset));
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [offset]);
  return height;
}

/**
 * 执行日志抽屉（§8.2 / T3.3、T3.4）：
 * - 宽 50%，上半部 Descriptions（结束时间/耗时仅终态显示）；
 * - 下半部日志明细从新到旧，行格式 {i}. {内容} {时间}，内容级别着色、单行省略号悬浮 Tooltip、
 *   时间完整显示右对齐灰色等宽；虚拟滚动（antd Table virtual，等效 List virtual）支撑几千条日志；
 * - RUNNING：标题栏刷新按钮（旋转加载态）+ 打开期间 30s 自动轮询，关闭即停；终态不显示刷新按钮。
 */
export default function ExecutionDrawer({ executionId, onClose, onUpdated }: ExecutionDrawerProps) {
  const open = executionId != null;
  const [detail, setDetail] = useState<ExecutionDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const onUpdatedRef = useRef(onUpdated);
  onUpdatedRef.current = onUpdated;

  const fetchDetail = useCallback(
    async (silent = false) => {
      if (executionId == null) return;
      if (silent) setRefreshing(true);
      else setLoading(true);
      try {
        const data = await fetchExecutionDetail(executionId);
        setDetail(data);
        onUpdatedRef.current?.();
      } catch {
        // 静默失败：保留旧数据，等待下次手动/自动刷新
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [executionId],
  );

  // 打开时拉取详情，关闭即清空（同时停掉轮询）
  useEffect(() => {
    if (!open) {
      setDetail(null);
      return;
    }
    void fetchDetail();
  }, [open, fetchDetail]);

  const execution = detail?.execution;
  const isRunning = execution?.status === 'RUNNING';

  // RUNNING 打开期间每 30s 自动轮询；关闭或转终态（依赖条件失效）自动停止
  useEffect(() => {
    if (!open || !isRunning) return;
    const timer = window.setInterval(() => void fetchDetail(true), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [open, isRunning, fetchDetail]);

  const listHeight = useViewportLogHeight(430);

  // 日志明细列：{seq}. {内容} {时间}，序号倒序——最新一条显示最大 seq，往下递减（服务端已按 seq DESC 排好）
  const logColumns: ColumnsType<ExecutionLog> = [
    {
      title: '#',
      key: 'index',
      width: 56,
      render: (_, record, index) => <span className="mono">{record.seq ?? index + 1}.</span>,
    },
    {
      title: '日志内容',
      key: 'message',
      ellipsis: { showTitle: false },
      render: (_, record) => <LogLevelText level={record.level} message={record.message} />,
    },
    {
      title: '时间',
      key: 'time',
      width: 165,
      align: 'right',
      render: (_, record) => (
        <span className="mono" style={{ color: 'rgba(0, 0, 0, 0.45)', fontSize: 12 }}>
          {record.logTime}
        </span>
      ),
    },
  ];

  const descItems: DescriptionsProps['items'] = [];
  if (execution) {
    descItems.push(
      {
        key: 'rpaMessageId',
        label: '消息ID',
        children: (
          <Typography.Text
            className="mono"
            copyable={{ text: execution.rpaMessageId }}
            style={{ color: 'rgba(0, 0, 0, 0.88)' }}
          >
            {execution.rpaMessageId}
          </Typography.Text>
        ),
      },
      { key: 'jobId', label: 'JobId', children: <span className="mono">{execution.jobId}</span> },
      { key: 'queueName', label: '队列名', children: <span className="mono">{execution.queueName}</span> },
      { key: 'deviceName', label: '设备名', children: execution.deviceName },
      { key: 'status', label: '执行状态', children: <StatusTag status={execution.status} /> },
      { key: 'createTime', label: '创建时间', children: <span className="mono">{execution.createTime}</span> },
    );
    // 结束时间与耗时仅终态展示（§8.2）
    if (isFinalStatus(execution.status)) {
      descItems.push(
        {
          key: 'finishedAt',
          label: '结束时间',
          children: <span className="mono">{execution.finishedAt ?? '—'}</span>,
        },
        {
          key: 'duration',
          label: '耗时',
          children: <span className="mono">{formatDuration(execution.durationSeconds)}</span>,
        },
      );
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="50%"
      title={
        <Space size={8}>
          执行日志
          {execution && <StatusTag status={execution.status} />}
        </Space>
      }
      extra={
        isRunning ? (
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined spin={refreshing} />}
            disabled={refreshing}
            onClick={() => void fetchDetail(true)}
          >
            刷新最新日志
          </Button>
        ) : null
      }
    >
      <Spin spinning={loading && !detail}>
        {execution && (
          <Descriptions
            bordered
            size="small"
            column={{ xs: 1, md: 2 }}
            items={descItems}
            style={{ marginBottom: 16 }}
          />
        )}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
          <span style={{ fontWeight: 600 }}>日志明细</span>
          <span style={{ color: 'rgba(0, 0, 0, 0.45)', fontSize: 12 }}>
            从新到旧 · 共 {detail?.logs.length ?? 0} 条
          </span>
        </div>
        <Table<ExecutionLog>
          virtual
          rowKey="seq"
          size="small"
          columns={logColumns}
          dataSource={detail?.logs ?? []}
          pagination={false}
          scroll={{ x: 640, y: listHeight }}
        />
      </Spin>
    </Drawer>
  );
}
