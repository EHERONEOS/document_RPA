import { Navigate, Route, Routes } from 'react-router-dom';
import AdminLayout from './layouts/AdminLayout';
import DeviceManagePage from './pages/DeviceManagePage';
import LogListPage from './pages/LogListPage';
import QueueManagePage from './pages/QueueManagePage';

// 路由骨架：设备管理为默认首页；设备管理仅配置/查看设备，队列的分配与控制在队列管理页
export default function App() {
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route path="/device-manage" element={<DeviceManagePage />} />
        <Route path="/queue-manage" element={<QueueManagePage />} />
        <Route path="/logs" element={<LogListPage />} />
        {/* 旧「设备运行 / 队列运行」页面已移除，兼容旧地址跳转 */}
        <Route path="/devices" element={<Navigate to="/device-manage" replace />} />
        <Route path="/queues" element={<Navigate to="/queue-manage" replace />} />
        <Route path="*" element={<Navigate to="/device-manage" replace />} />
      </Route>
    </Routes>
  );
}
