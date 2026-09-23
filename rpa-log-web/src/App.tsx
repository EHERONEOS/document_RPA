import { Navigate, Route, Routes } from 'react-router-dom';
import AdminLayout from './layouts/AdminLayout';
import DeviceListPage from './pages/DeviceListPage';
import DeviceManagePage from './pages/DeviceManagePage';
import LogListPage from './pages/LogListPage';
import QueueListPage from './pages/QueueListPage';

// 路由骨架（§8.1）：设备管理为默认首页；各页面由 M3 任务逐个实现
export default function App() {
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route path="/device-manage" element={<DeviceManagePage />} />
        <Route path="/logs" element={<LogListPage />} />
        <Route path="/devices" element={<DeviceListPage />} />
        <Route path="/queues" element={<QueueListPage />} />
        <Route path="*" element={<Navigate to="/device-manage" replace />} />
      </Route>
    </Routes>
  );
}
