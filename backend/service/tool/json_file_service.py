import json
import os
from pathlib import Path
from typing import Dict, Any, List
from quart import jsonify
import aiofiles


class JsonFileService:
    """
    JSON文件服务类，用于读取指定目录下的JSON文件
    """

    def __init__(self, data_directory: str = "mock"):
        """
        初始化JSON文件服务
        
        Args:
            data_directory: 数据目录路径，默认为"mock"
        """
        self.data_directory = Path(data_directory)
        self._ensure_directory_exists()

    def _ensure_directory_exists(self) -> None:
        """确保数据目录存在"""
        if not self.data_directory.exists():
            self.data_directory.mkdir(parents=True)

    async def list_files(self) -> List[Dict[str, Any]]:
        """
        列出目录下所有JSON文件
        
        Returns:
            包含文件信息的列表
        """
        json_files = []
        for file_path in self.data_directory.glob("*.json"):
            stat = file_path.stat()
            json_files.append({
                'name': file_path.name,
                'size': stat.st_size,
                'modified': stat.st_mtime
            })
        return json_files

    async def read_json_file(self, filename: str) -> Dict[str, Any]:
        """
        读取指定JSON文件
        
        Args:
            filename: 文件名
            
        Returns:
            JSON文件内容
            
        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件不是JSON格式
        """
        if not filename.endswith('.json'):
            raise ValueError("只支持JSON文件")

        file_path = self.data_directory / filename
        if not file_path.exists():
            raise FileNotFoundError(f"文件 {filename} 不存在")

        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content)