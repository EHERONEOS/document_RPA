import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  extra?: ReactNode;
}

/** 页面标题区（对照原型 page-header：20px 标题 + 灰色描述） */
export default function PageHeader({ title, description, extra }: PageHeaderProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'space-between',
        marginBottom: 16,
      }}
    >
      <div>
        <div style={{ fontSize: 20, fontWeight: 600, lineHeight: '28px' }}>{title}</div>
        {description && (
          <div style={{ color: 'rgba(0, 0, 0, 0.45)', marginTop: 4 }}>{description}</div>
        )}
      </div>
      {extra}
    </div>
  );
}
