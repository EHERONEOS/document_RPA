import { SearchOutlined, UndoOutlined } from '@ant-design/icons';
import { Button, Form, Input, Select } from 'antd';
import type { FormInstance } from 'antd';
import { useEffect, useRef } from 'react';
import type { ExecutionStatus } from '../../api/types';

/** 搜索条件（§8.2：消息ID/JobId 后缀模糊，队列名/执行状态精确） */
export interface SearchValues {
  rpaMessageId?: string;
  jobId?: string;
  queueName?: string;
  status?: ExecutionStatus;
}

interface SearchFormProps {
  form: FormInstance<SearchValues>;
  /** 队列下拉选项（来自 GET /api/v1/queues） */
  queueOptions: string[];
  initialValues?: SearchValues;
  /** 值变化（防抖 300ms 后触发）或点击查询 */
  onChange: (values: SearchValues) => void;
  /** 点击重置（表单回到 initialValues 后触发，供父级清理隐藏筛选） */
  onReset?: () => void;
}

const STATUS_OPTIONS: { value: ExecutionStatus; label: string }[] = [
  { value: 'SUCCESS', label: '成功' },
  { value: 'FAILED', label: '失败' },
  { value: 'RUNNING', label: '运行中' },
  { value: 'TIMEOUT', label: '超时' },
];

/** 去掉首尾空格并丢弃空值 */
function trimValues(values: SearchValues): SearchValues {
  const result: SearchValues = {};
  const messageId = values.rpaMessageId?.trim();
  const jobId = values.jobId?.trim();
  if (messageId) result.rpaMessageId = messageId;
  if (jobId) result.jobId = jobId;
  if (values.queueName) result.queueName = values.queueName;
  if (values.status) result.status = values.status;
  return result;
}

/** 搜索表单：输入即防抖 300ms 查询 + 查询/重置按钮（§8.2） */
export default function SearchForm({ form, queueOptions, initialValues, onChange, onReset }: SearchFormProps) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const onChangeRef = useRef(onChange);
  const onResetRef = useRef(onReset);
  onChangeRef.current = onChange;
  onResetRef.current = onReset;

  const scheduleChange = (values: SearchValues) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => onChangeRef.current(trimValues(values)), 300);
  };

  // 卸载时清理未触发的防抖
  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  const handleSearch = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    onChangeRef.current(trimValues(form.getFieldsValue()));
  };

  const handleReset = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    form.resetFields();
    onChangeRef.current(trimValues(form.getFieldsValue()));
    onResetRef.current?.();
  };

  return (
    <Form
      form={form}
      layout="inline"
      initialValues={initialValues}
      onValuesChange={(_, values) => scheduleChange(values as SearchValues)}
    >
      <Form.Item name="rpaMessageId" label="消息ID">
        <Input placeholder="消息ID后缀模糊匹配" allowClear style={{ width: 220 }} />
      </Form.Item>
      <Form.Item name="jobId" label="JobId">
        <Input placeholder="JobId / 提单号后缀匹配" allowClear style={{ width: 200 }} />
      </Form.Item>
      <Form.Item name="queueName" label="队列名">
        <Select
          placeholder="全部队列"
          allowClear
          showSearch
          optionFilterProp="label"
          style={{ width: 200 }}
          options={queueOptions.map((name) => ({ label: name, value: name }))}
        />
      </Form.Item>
      <Form.Item name="status" label="执行状态">
        <Select placeholder="全部状态" allowClear style={{ width: 130 }} options={STATUS_OPTIONS} />
      </Form.Item>
      <Form.Item>
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
          查询
        </Button>
      </Form.Item>
      <Form.Item>
        <Button icon={<UndoOutlined />} onClick={handleReset}>
          重置
        </Button>
      </Form.Item>
    </Form>
  );
}
