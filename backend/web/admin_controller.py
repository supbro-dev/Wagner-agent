import json

from flask import Blueprint, jsonify, request

import container
from dao import query_data_task_dao
from model.query_data_task_detail import QueryDataTaskDetail
from model.response import success
from web.data_analyst_controller import get_or_create_data_analyst_service
from web.vo.result_vo import ResultVo

adminApi = Blueprint('admin', __name__)

@adminApi.route('/addAllTask2Vector', methods=['GET'])
def add_all_task_2_vector():
    business_key = request.args.get('businessKey')

    data_analyst_service = get_or_create_data_analyst_service(business_key)
    task_list = container.dao_container.query_data_task_dao().get_all_tasks(business_key)

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

    data_analyst_service.vector_store.add_texts(texts=texts, metadatas=metadatas)

    result = ResultVo(success=True,result="加载完成")
    return jsonify(success(result).to_dict())

