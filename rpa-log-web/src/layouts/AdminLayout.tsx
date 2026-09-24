import {
  ApiOutlined,
  DesktopOutlined,
  FileTextOutlined,
  HomeOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { Breadcrumb, Layout, Menu, Tag, theme } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import '../components/console.css';

const { Sider, Header, Content } = Layout;

// 菜单与路由映射（§8.1：白色 Sider + Header 面包屑 + Content #f5f5f5）
const MENU_ITEMS = [
  { key: '/device-manage', icon: <DesktopOutlined />, label: '设备管理', breadcrumb: '设备管理' },
  { key: '/queue-manage', icon: <ApiOutlined />, label: '队列管理', breadcrumb: '队列管理' },
  { key: '/logs', icon: <FileTextOutlined />, label: '日志列表', breadcrumb: '日志列表' },
];

/** T0.3：控制台整体框架（M3 按原型填充各页面）。 */
export default function AdminLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { token } = theme.useToken();

  const current = MENU_ITEMS.find((item) => location.pathname.startsWith(item.key));

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={208} style={{ background: '#fff', borderRight: `1px solid ${token.colorBorderSecondary}` }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '16px 16px',
            fontWeight: 600,
            fontSize: 16,
            color: token.colorPrimary,
          }}
        >
          <RobotOutlined />
          RPA 控制台
        </div>
        <Menu
          mode="inline"
          selectedKeys={current ? [current.key] : []}
          items={MENU_ITEMS.map(({ key, icon, label }) => ({ key, icon, label }))}
          onClick={({ key }) => navigate(key)}
          style={{ borderInlineEnd: 'none' }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <Breadcrumb
            items={[
              { title: <HomeOutlined /> , href: '#/logs' },
              { title: current?.breadcrumb ?? '日志列表' },
            ]}
          />
          <Tag color="blue">本地开发</Tag>
        </Header>
        <Content style={{ margin: 16 }}>
          {/* 各页面自行组合白色卡片（对照原型：#f5f5f5 画布 + 白色容器） */}
          <div style={{ minHeight: 360 }}>
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
