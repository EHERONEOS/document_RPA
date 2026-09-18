-- 创建部署控制专用库，不修改原队列控制库。
CREATE DATABASE IF NOT EXISTS queue_control_deploy
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;
