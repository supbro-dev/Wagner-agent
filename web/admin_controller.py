import json

from flask import Blueprint, jsonify, request
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_redis import RedisConfig, RedisVectorStore

from config import Config
from dao import query_data_task_dao
from model.query_data_task_detail import QueryDataTaskDetail
from model.response import success
from service.agent.workflow_service import get_workflow
from service.tool.wagner.wagner_service import make_work_group_business_key
from web.vo.result_vo import ResultVo
from web.work_group_agent_controller import get_or_create_workflow_service

adminApi = Blueprint('admin', __name__)

@adminApi.route('/addAllTask2Vector', methods=['GET'])
def add_all_task_2_vector():
    workplace_code = request.args.get('workplaceCode')
    work_group_code = request.args.get('workGroupCode')

    workflow_service = get_or_create_workflow_service(workplace_code, work_group_code)

    business_key = make_work_group_business_key(workplace_code, work_group_code)
    task_list = query_data_task_dao.get_all_tasks(business_key)

    texts = []
    metadatas = []
    for task in task_list:
        detail = QueryDataTaskDetail.model_validate(json.loads(task.task_detail))
        texts.append(f"任务名称：{task.name}\n任务目标：{detail.target}")
        metadatas.append({
                "task_id": task.id,
                "task_name": task.name,
                "task_detail": task.task_detail
            })

    workflow_service.vector_store.add_texts(texts=texts, metadatas=metadatas)

    result = ResultVo(result="加载完成")
    return jsonify(success(result).to_dict())
