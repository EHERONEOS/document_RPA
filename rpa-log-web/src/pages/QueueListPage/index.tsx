import { Card, Table, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchQueues } from '../../api/queues';
import type { QueueInfo } from '../../api/types';
import PageHeader from '../../components/PageHeader';
import { formatDuration, formatRate } from '../../utils/format';

/** 队列列表页（§8.3 / T3.6）：行点击下钻日志列表（队列下拉选中该队列） */
export default function QueueListPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<QueueInfo[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchQueues()
      .then((list) => {
        if (!cancelled) setData(list);
      })
      .catch((error) => {
        if (!cancelled) message.error(error instanceof Error ? error.message : '加载队列列表失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const columns: ColumnsType<QueueInfo> = [
    {
      title: '队列名',
      dataIndex: 'queueName',
      render: (_, record) => (
        <span className="mono" style={{ fontWeight: 600 }}>
          {record.queueName}
        </span>
      ),
    },
    { title: '客户', dataIndex: 'customerCode', width: 100 },
    { title: '船司', dataIndex: 'carrierCode', width: 100 },
    { title: '业务', dataIndex: 'businessCode', width: 100 },
    { title: '今日执行', dataIndex: 'todayCount', width: 100 },
    {
      title: '成功率',
      dataIndex: 'successRate',
      width: 100,
      render: (_, record) => <span className="mono">{formatRate(record.successRate)}</span>,
    },
    {
      title: '平均耗时',
      dataIndex: 'avgDurationSeconds',
      width: 110,
      render: (_, record) => <span className="mono">{formatDuration(record.avgDurationSeconds)}</span>,
    },
  ];

  return (
    <div>
      <PageHeader
        title="队列列表"
        description="展示接入日志服务的业务队列及执行统计，点击行可查看该队列的执行日志"
      />
      <Card size="small">
        <Table<QueueInfo>
          rowKey="queueName"
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={data}
          pagination={data.length > 10 ? { pageSize: 10, showTotal: (t) => `共 ${t} 个` } : false}
          onRow={(record) => ({
            onClick: () => navigate('/logs', { state: { queueName: record.queueName } }),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>
    </div>
  );
}
