from quart import Blueprint, jsonify, request

from model.response import success
from service.tool.json_file_service import JsonFileService
import os

from web.vo.result_vo import ResultVo

# 创建蓝图
jsonFileApi = Blueprint('jsonFileApi', __name__)

# 初始化服务，使用项目目录下的mock文件夹
json_file_service = JsonFileService(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'mock'))


@jsonFileApi.route('/<filename>', methods=['GET'])
async def get_file_content(filename):
    """
    获取指定JSON文件的内容
    
    Args:
        filename: 文件名
    """
    try:
        content = await json_file_service.read_json_file(filename)
        return jsonify(content)
    except Exception as e:
        result = ResultVo(success=False, result=str(e))
        return jsonify(success(result).to_dict())
