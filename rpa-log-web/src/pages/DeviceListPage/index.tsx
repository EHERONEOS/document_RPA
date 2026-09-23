import { Card, Table, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchDevices } from '../../api/devices';
import type { DeviceInfo } from '../../api/types';
import PageHeader from '../../components/PageHeader';
import { formatRate } from '../../utils/format';

/** 设备列表页（§8.3 / T3.6）：行点击下钻日志列表（设备名作为隐藏筛选） */
export default function DeviceListPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<DeviceInfo[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchDevices()
      .then((list) => {
        if (!cancelled) setData(list);
      })
      .catch((error) => {
        if (!cancelled) message.error(error instanceof Error ? error.message : '加载设备列表失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const columns: ColumnsType<DeviceInfo> = [
    {
      title: '设备名',
      dataIndex: 'deviceName',
      render: (_, record) => <span style={{ fontWeight: 600 }}>{record.deviceName}</span>,
    },
    {
      title: '操作系统',
      dataIndex: 'osInfo',
      render: (_, record) => record.osInfo || '—',
    },
    { title: '绑定队列数', dataIndex: 'boundQueueCount', width: 110 },
    { title: '今日执行', dataIndex: 'todayCount', width: 100 },
    {
      title: '成功率',
      dataIndex: 'successRate',
      width: 100,
      render: (_, record) => <span className="mono">{formatRate(record.successRate)}</span>,
    },
    {
      title: '最近心跳',
      dataIndex: 'lastSeenAt',
      width: 170,
      render: (_, record) => <span className="mono">{record.lastSeenAt || '—'}</span>,
    },
    {
      title: '在线状态',
      dataIndex: 'online',
      width: 100,
      render: (_, record) =>
        record.online ? (
          <Tag color="success" style={{ marginInlineEnd: 0 }}>
            在线
          </Tag>
        ) : (
          <Tag style={{ marginInlineEnd: 0 }}>离线</Tag>
        ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="设备列表"
        description="展示接入日志服务的 RPA 执行机器及最近执行情况，点击行可查看该设备的执行日志"
      />
      <Card size="small">
        <Table<DeviceInfo>
          rowKey="deviceName"
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={data}
          pagination={data.length > 10 ? { pageSize: 10, showTotal: (t) => `共 ${t} 台` } : false}
          onRow={(record) => ({
            onClick: () => navigate('/logs', { state: { deviceName: record.deviceName } }),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>
    </div>
  );
}
