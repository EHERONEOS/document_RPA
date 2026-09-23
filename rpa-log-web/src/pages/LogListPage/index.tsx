import { Card, Col, Form, Row, Switch, Tag, message } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { fetchExecutions } from '../../api/executions';
import { fetchQueues } from '../../api/queues';
import { fetchStatsSummary } from '../../api/stats';
import type { Execution, ExecutionStatus, StatsSummary } from '../../api/types';
import PageHeader from '../../components/PageHeader';
import ExecutionDrawer from './ExecutionDrawer';
import ExecutionTable from './ExecutionTable';
import FailReasonModal from './FailReasonModal';
import RecordFilesModal from './RecordFilesModal';
import SearchForm from './SearchForm';
import type { SearchValues } from './SearchForm';

const POLL_INTERVAL_MS = 30_000;

/** 设备/队列页下钻跳转携带的 state（§8.3：队列→下拉筛选；设备→隐藏筛选） */
interface NavState {
  deviceName?: string;
  queueName?: string;
}

interface StatCardConfig {
  key: string;
  label: string;
  value: number | null;
  color: string;
  hint: string;
  /** 点击应用的执行状态筛选；undefined = 清空状态筛选 */
  applyStatus?: ExecutionStatus;
}

/** 日志列表页（§8.2 核心页 / T3.2）：统计卡 + 搜索 + 表格 + 30s 轮询 + 抽屉/弹窗 */
export default function LogListPage() {
  const location = useLocation();
  const [form] = Form.useForm<SearchValues>();

  // 下钻带入的初始筛选：队列名进搜索表单；设备名为隐藏筛选（仅 Tag 提示）
  const nav = (location.state ?? null) as NavState | null;
  const [filters, setFilters] = useState<SearchValues>(() => (nav?.queueName ? { queueName: nav.queueName } : {}));
  const [deviceName, setDeviceName] = useState<string | undefined>(() => nav?.deviceName || undefined);
  const [initialValues] = useState<SearchValues>(() => (nav?.queueName ? { queueName: nav.queueName } : {}));

  const [list, setList] = useState<Execution[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [stats, setStats] = useState<StatsSummary | null>(null);
  const [queueOptions, setQueueOptions] = useState<string[]>([]);
  const [pollingEnabled, setPollingEnabled] = useState(true);

  const [drawerId, setDrawerId] = useState<number | null>(null);
  const [failRow, setFailRow] = useState<Execution | null>(null);
  const [filesId, setFilesId] = useState<number | null>(null);

  const fetchList = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      try {
        const data = await fetchExecutions({ page, pageSize, ...filters, deviceName });
        setList(data.list);
        setTotal(data.total);
      } catch (error) {
        if (!silent) message.error(error instanceof Error ? error.message : '加载执行记录失败');
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [page, pageSize, filters, deviceName],
  );

  const fetchStats = useCallback(async () => {
    try {
      setStats(await fetchStatsSummary());
    } catch {
      // 统计卡加载失败不打断主列表
    }
  }, []);

  useEffect(() => {
    void fetchList();
  }, [fetchList]);

  useEffect(() => {
    void fetchStats();
  }, [fetchStats]);

  // 队列下拉选项（§8.2：来自 /api/v1/queues）
  useEffect(() => {
    let cancelled = false;
    fetchQueues()
      .then((queues) => {
        if (!cancelled) setQueueOptions(queues.map((queue) => queue.queueName));
      })
      .catch(() => {
        // 下拉选项加载失败不阻塞页面
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const hasRunning = useMemo(() => list.some((row) => row.status === 'RUNNING'), [list]);

  // 存在 RUNNING 行且开关开启时，整表 30s 自动轮询（§8.2 辅助能力）
  useEffect(() => {
    if (!pollingEnabled || !hasRunning) return;
    const timer = window.setInterval(() => {
      void fetchList(true);
      void fetchStats();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [pollingEnabled, hasRunning, fetchList, fetchStats]);

  /** 搜索条件变化（防抖后）/点击查询：应用筛选并回到第 1 页 */
  const handleSearchChange = useCallback((values: SearchValues) => {
    setFilters(values);
    setPage(1);
  }, []);

  /** 重置：清空隐藏设备筛选（表单由 SearchForm 复位） */
  const handleReset = useCallback(() => {
    setDeviceName(undefined);
    setPage(1);
  }, []);

  /** 统计卡快捷筛选：再次点击同一状态可取消 */
  const applyStatusFilter = useCallback(
    (status?: ExecutionStatus) => {
      const next = filters.status === status ? undefined : status;
      form.setFieldValue('status', next);
      setFilters((prev) => ({ ...prev, status: next }));
      setPage(1);
    },
    [filters.status, form],
  );

  const successRate =
    stats && stats.todayTotal > 0 ? `${((stats.successCount / stats.todayTotal) * 100).toFixed(1)}%` : null;

  const statCards: StatCardConfig[] = [
    {
      key: 'total',
      label: '今日执行',
      value: stats?.todayTotal ?? null,
      color: '#1677ff',
      hint: '点击清空状态筛选',
    },
    {
      key: 'success',
      label: '成功',
      value: stats?.successCount ?? null,
      color: '#52c41a',
      hint: successRate ? `成功率 ${successRate}` : '点击筛选成功记录',
      applyStatus: 'SUCCESS',
    },
    {
      key: 'failed',
      label: '失败',
      value: stats?.failedCount ?? null,
      color: '#ff4d4f',
      hint: '点击筛选失败记录',
      applyStatus: 'FAILED',
    },
    {
      key: 'running',
      label: '运行中',
      value: stats?.runningCount ?? null,
      color: '#faad14',
      hint: '点击筛选运行中记录',
      applyStatus: 'RUNNING',
    },
  ];

  const drawerUpdated = useCallback(() => {
    void fetchList(true);
    void fetchStats();
  }, [fetchList, fetchStats]);

  return (
    <div>
      <PageHeader
        title="日志列表"
        description="按消息维度展示 RPA 任务执行记录，支持按消息 ID / JobId / 队列名 / 执行状态检索"
      />

      {/* 统计卡（T3.6 /stats/summary，运行中 warning 色，可点击快捷筛选） */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {statCards.map((card) => (
          <Col key={card.key} xs={24} sm={12} xl={6}>
            <Card
              size="small"
              className={card.applyStatus || card.key === 'total' ? 'stat-card-clickable' : undefined}
              onClick={() => applyStatusFilter(card.applyStatus)}
              styles={{ body: { padding: '16px 20px' } }}
            >
              <div style={{ color: 'rgba(0, 0, 0, 0.65)' }}>{card.label}</div>
              <div style={{ fontSize: 28, fontWeight: 600, marginTop: 8, color: card.color }}>
                {card.value ?? '—'}
              </div>
              <div style={{ fontSize: 12, color: 'rgba(0, 0, 0, 0.45)', marginTop: 6 }}>{card.hint}</div>
            </Card>
          </Col>
        ))}
      </Row>

      <Card size="small" style={{ marginBottom: 16 }}>
        <SearchForm
          form={form}
          queueOptions={queueOptions}
          initialValues={initialValues}
          onChange={handleSearchChange}
          onReset={handleReset}
        />
      </Card>

      <Card size="small">
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 8,
            marginBottom: 16,
          }}
        >
          <span style={{ fontSize: 16, fontWeight: 600 }}>执行记录</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            {deviceName && (
              <Tag
                key={deviceName}
                color="blue"
                closable
                onClose={(e) => {
                  e.preventDefault();
                  setDeviceName(undefined);
                  setPage(1);
                }}
              >
                设备：{deviceName}
              </Tag>
            )}
            {pollingEnabled && hasRunning && (
              <Tag color="warning" style={{ marginInlineEnd: 0 }}>
                <span className="running-dot" />
                30s 轮询中
              </Tag>
            )}
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'rgba(0, 0, 0, 0.65)' }}>
              30s 自动刷新
              <Switch
                size="small"
                checked={pollingEnabled}
                checkedChildren="开"
                unCheckedChildren="停"
                onChange={setPollingEnabled}
              />
            </span>
            <span style={{ color: 'rgba(0, 0, 0, 0.45)' }}>共 {total} 条</span>
          </div>
        </div>
        <ExecutionTable
          dataSource={list}
          total={total}
          page={page}
          pageSize={pageSize}
          loading={loading}
          onPageChange={(next, nextSize) => {
            if (nextSize !== pageSize) {
              setPage(1);
              setPageSize(nextSize);
            } else {
              setPage(next);
            }
          }}
          onView={(row) => setDrawerId(row.executionId)}
          onFailReason={(row) => setFailRow(row)}
          onFiles={(row) => setFilesId(row.executionId)}
        />
      </Card>

      <ExecutionDrawer executionId={drawerId} onClose={() => setDrawerId(null)} onUpdated={drawerUpdated} />
      <FailReasonModal execution={failRow} onClose={() => setFailRow(null)} />
      <RecordFilesModal executionId={filesId} onClose={() => setFilesId(null)} />
    </div>
  );
}
