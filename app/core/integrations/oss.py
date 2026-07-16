import os
import requests
from pathlib import Path
from app.core.logging.logger import Logger



class OssClient:
    """截图和录屏文件地址处理。"""
    url = 'https://fec.cgofish.com/v1/file/upload'
    def __init__(self):
        self.logger = Logger()

    def oss_upload(self, file_path,is_remove= True):
        """上传文件到OSS。"""
        retry = 3   
        if "mp4" in file_path or "zip" in file_path:
            retry = 1
        for i in range(retry):
            try:
                if not isinstance(file_path, (str, bytes, os.PathLike)) or not os.path.isfile(file_path):
                    self.logger.error(f"文件路径 {file_path} 不存在")
                    return None
                with open(file_path, 'rb') as file:  # 自动管理文件关闭
                    response = requests.post(self.url, files={'file': file}, timeout=60)
                if response.status_code == 200:
                    data = response.json().get('data')
                    if is_remove:
                        os.remove(file_path)
                    self.logger.info(f"上传文件成功，接口响应：{data}")
                    return data.get("url")
                else:
                    self.logger.error(f"上传文件到OSS 失败: 状态码 {response.status_code}")
                    pass
            except Exception as e:
                self.logger.error(f"上传文件到OSS 失败: 重试{i+1}/{retry}")
                pass
