import { Button, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { Execution } from '../../api/types';
import { formatDuration, isFinalStatus } from '../../utils/format';
import StatusTag from './StatusTag';

interface ExecutionTableProps {
  dataSource: Execution[];
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  onPageChange: (page: number, pageSize: number) => void;
  onView: (row: Execution) => void;
  onFailReason: (row: Execution) => void;
  onFiles: (row: Execution) => void;
}

/**
 * 执行记录表格（§8.2）：后端分页 10/20/50，
 * RUNNING 行结束时间/耗时显示 —；操作列按状态显隐。
 */
export default function ExecutionTable({
  dataSource,
  total,
  page,
  pageSize,
  loading,
  onPageChange,
  onView,
  onFailReason,
  onFiles,
}: ExecutionTableProps) {
  const columns: ColumnsType<Execution> = [
    {
      title: '消息ID',
      dataIndex: 'rpaMessageId',
      width: 250,
      render: (_, record) => (
        <Typography.Text
          className="mono"
          copyable={{ text: record.rpaMessageId, tooltips: ['复制消息ID', '已复制'] }}
          style={{ color: 'rgba(0, 0, 0, 0.88)' }}
        >
          {record.rpaMessageId}
        </Typography.Text>
      ),
    },
    {
      title: 'JobId',
      dataIndex: 'jobId',
      width: 160,
      render: (_, record) => <span className="mono">{record.jobId}</span>,
    },
    {
      title: '队列名',
      dataIndex: 'queueName',
      width: 150,
      ellipsis: true,
      render: (_, record) => (
        <span className="mono" title={record.queueName}>
          {record.queueName}
        </span>
      ),
    },
    {
      title: '设备名',
      dataIndex: 'deviceName',
      width: 130,
      ellipsis: true,
    },
    {
      title: '执行状态',
      dataIndex: 'status',
      width: 100,
      render: (_, record) => <StatusTag status={record.status} />,
    },
    {
      title: '创建时间',
      dataIndex: 'createTime',
      width: 165,
      render: (_, record) => <span className="mono">{record.createTime}</span>,
    },
    {
      title: '结束时间',
      dataIndex: 'finishedAt',
      width: 165,
      render: (_, record) => (
        <span className="mono">{record.status === 'RUNNING' ? '—' : (record.finishedAt ?? '—')}</span>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'durationSeconds',
      width: 90,
      render: (_, record) => (
        <span className="mono">{record.status === 'RUNNING' ? '—' : formatDuration(record.durationSeconds)}</span>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      fixed: 'right',
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" style={{ padding: 0 }} onClick={() => onView(record)}>
            查看详情
          </Button>
          {record.status === 'FAILED' && (
            <Button type="link" size="small" danger style={{ padding: 0 }} onClick={() => onFailReason(record)}>
              失败原因
            </Button>
          )}
          {isFinalStatus(record.status) && (
            <Button type="link" size="small" style={{ padding: 0 }} onClick={() => onFiles(record)}>
              记录文件
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Table<Execution>
      rowKey="executionId"
      size="middle"
      loading={loading}
      columns={columns}
      dataSource={dataSource}
      scroll={{ x: 1280 }}
      pagination={{
        current: page,
        pageSize,
        total,
        showSizeChanger: true,
        pageSizeOptions: [10, 20, 50],
        showQuickJumper: true,
        onChange: onPageChange,
      }}
    />
  );
}
