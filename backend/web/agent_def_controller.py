from marshmallow import fields
from quart import g, Blueprint, jsonify

from container import service_container
from model.response import success, failure_with_ex
from service.agent.agent_def_service import AgentDefService
from dao.agent_def_dao import AgentDefDAO
from web.validate.validator import validate_json_params, validate_query_params
from web.vo.result_vo import ResultVo
from web.vo.agent_def_vo import AgentDefVO
from web.vo.page_result_vo import PageResultVO, Page

# 创建蓝图
agent_def_api = Blueprint('agent_def', __name__)

@agent_def_api.route('create', methods=['POST'])
@validate_json_params(
    businessKey=fields.Str(required=True),
    name=fields.Str(required=True),
    systemPrompt=fields.Str(required=False),
    agentType=fields.Str(required=True)
)
async def create_agent_def():
    """
    创建新的Agent定义
    """
    try:
        business_key = g.validated_data['businessKey']
        name = g.validated_data['name']
        system_prompt = g.validated_data['systemPrompt']
        agent_type = g.validated_data['agentType']

        # 创建Agent定义
        agent_def = service_container.agent_def_service().create_agent_def(business_key, name, system_prompt, agent_type)

        result = ResultVo(success=True, result="保存成功")

        return jsonify(success(result).to_dict())
    except Exception as e:
        return jsonify(failure_with_ex(e).to_dict())


@agent_def_api.route('/update', methods=['PUT'])
@validate_json_params(
    agentId=fields.Int(required=True),
    businessKey=fields.Str(required=False),
    name=fields.Str(required=False),
    systemPrompt=fields.Str(required=False),
    agentType=fields.Str(required=False)
)
async def update_agent_def():
    """
    更新Agent定义
    """
    try:
        agent_id = g.validated_data['agentId']
        business_key = g.validated_data.get('businessKey')
        name = g.validated_data.get('name')
        system_prompt = g.validated_data.get('systemPrompt')
        agent_type = g.validated_data.get('agentType')

        # 更新Agent定义
        agent_def = service_container.agent_def_service().update_agent_def(
            agent_id, 
            business_key=business_key, 
            name=name, 
            system_prompt=system_prompt, 
            agent_type=agent_type
        )

        result = ResultVo(success=True, result="更新成功")

        return jsonify(success(result).to_dict())
    except Exception as e:
        return jsonify(failure_with_ex(e).to_dict())


@agent_def_api.route('/delete', methods=['DELETE'])
@validate_json_params(
    agentId=fields.Int(required=True)
)
async def delete_agent_def():
    """
    删除Agent定义
    """
    try:
        agent_id = g.validated_data['agentId']
        result = service_container.agent_def_service().delete_agent_def(agent_id)

        if result:
            result = ResultVo(success=True, result="删除成功")
            return jsonify(success(result).to_dict())
        else:
            result = ResultVo(success=False, result="未找到对应记录")
            return jsonify(success(result).to_dict())
    except Exception as e:
        return jsonify(failure_with_ex(e).to_dict())


@agent_def_api.route('/getById', methods=['GET'])
@validate_query_params(
    agentId=fields.Int(required=True)
)
async def get_agent_def():
    """
    根据ID获取Agent定义
    """
    try:
        agent_id = g.validated_data['agentId']
        agent_def = service_container.agent_def_service().get_agent_def_by_id(agent_id)

        if not agent_def:
            result = ResultVo(success=False, result="未找到对应记录")
            return jsonify(success(result).to_dict())

        # 转换为AgentVO对象
        agent_vo = AgentDefVO(
            id=agent_def.id,
            business_key=agent_def.business_key,
            name=agent_def.name,
            system_prompt=agent_def.system_prompt,
            agent_type=agent_def.agent_type,
        )

        result = ResultVo(success=True, result=agent_vo)
        return jsonify(success(result).to_dict())
    except Exception as e:
        return jsonify(failure_with_ex(e).to_dict())


@agent_def_api.route('list', methods=['GET'])
@validate_query_params(
    businessKey=fields.Str(required=True),
    name=fields.Str(required=False),
    agentType=fields.Str(required=False),
    page=fields.Int(required=False, missing=1),
    pageSize=fields.Int(required=False, missing=20)
)
async def list_agent_defs():
    """
    列出符合条件的Agent定义
    支持根据business_key、name、agent_type查询
    """
    try:
        # 获取查询参数
        business_key = g.validated_data['businessKey']
        name = g.validated_data['name']
        agent_type = g.validated_data['agentType']
        page = g.validated_data['page']
        page_size = g.validated_data['pageSize']
        page_size = min(page_size, 100)  # 限制最大页面大小

        # 查询数据
        agent_defs = service_container.agent_def_service().list_agent_defs(
            business_key=business_key,
            name=name,
            agent_type=agent_type,
            page=page,
            page_size=page_size
        )

        # 转换为AgentVO列表
        agent_vos = []
        for agent_def in agent_defs:
            agent_vo = AgentDefVO(
                id=agent_def.id,
                business_key=agent_def.business_key,
                name=agent_def.name,
                system_prompt=agent_def.system_prompt,
                agent_type=agent_def.agent_type,
            )
            agent_vos.append(agent_vo.to_dict())

        # 使用PageResultVO封装分页数据
        page_result = PageResultVO[AgentDefVO](
            success=True,
            list=agent_vos,
            pagination=Page(
                page=page,
                page_size=page_size,
                total=len(agent_vos)  # 注意：实际项目中应该返回总记录数
            )
        )

        return jsonify(success(page_result).to_dict())
    except Exception as e:
        return jsonify(failure_with_ex(e).to_dict())