from marshmallow import fields
from quart import g, Blueprint, jsonify

from container import service_container
from model.response import success, failure_with_ex
from service.tool.llm_tool_service import LLMToolService
from dao.llm_tool_dao import LLMToolDAO
from web.validate.validator import validate_json_params, validate_query_params
from web.vo.result_vo import ResultVo
from web.vo.llm_tool_vo import LLMToolVO
from web.vo.page_result_vo import PageResultVO, Page
from util.datetime_util import format_datatime

# 创建蓝图
llm_tool_api = Blueprint('llm_tool', __name__)

@llm_tool_api.route('/create', methods=['POST'])
@validate_json_params(
    name=fields.Str(required=True),
    description=fields.Str(required=True),
    argsDict=fields.Str(required=True),
    toolType=fields.Str(required=True),
    content=fields.Str(required=True),
    requestHandleScript=fields.Str(required=False),
    responseHandleScript=fields.Str(required=False)
)
async def create_llm_tool():
    """
    创建新的LLM工具
    """
    try:
        name = g.validated_data['name']
        description = g.validated_data['description']
        args_dict = g.validated_data['argsDict']
        tool_type = g.validated_data['toolType']
        content = g.validated_data['content']
        request_handle_script = g.validated_data.get('requestHandleScript')
        response_handle_script = g.validated_data.get('responseHandleScript')

        # 创建LLM工具
        llm_tool = service_container.llm_tool_service().create_llm_tool(
            name, description, args_dict, tool_type, content, 
            request_handle_script, response_handle_script)

        result = ResultVo(success=True, result="保存成功")

        return jsonify(success(result).to_dict())
    except Exception as e:
        return jsonify(failure_with_ex(e).to_dict())


@llm_tool_api.route('/update', methods=['POST'])
@validate_json_params(
    toolId=fields.Int(required=True),
    name=fields.Str(required=False),
    description=fields.Str(required=False),
    argsDict=fields.Str(required=False),
    toolType=fields.Str(required=False),
    content=fields.Str(required=False),
    requestHandleScript=fields.Str(required=False),
    responseHandleScript=fields.Str(required=False)
)
async def update_llm_tool():
    """
    更新LLM工具
    """
    try:
        tool_id = g.validated_data['toolId']
        name = g.validated_data.get('name')
        description = g.validated_data.get('description')
        args_dict = g.validated_data.get('argsDict')
        tool_type = g.validated_data.get('toolType')
        content = g.validated_data.get('content')
        request_handle_script = g.validated_data.get('requestHandleScript')
        response_handle_script = g.validated_data.get('responseHandleScript')

        # 更新LLM工具
        service_container.llm_tool_service().update_llm_tool(
            tool_id,
            name=name,
            description=description,
            args_dict=args_dict,
            tool_type=tool_type,
            content=content,
            request_handle_script=request_handle_script,
            response_handle_script=response_handle_script
        )

        result = ResultVo(success=True, result="更新成功")

        return jsonify(success(result).to_dict())
    except Exception as e:
        return jsonify(failure_with_ex(e).to_dict())


@llm_tool_api.route('/delete', methods=['POST'])
@validate_json_params(
    toolId=fields.Int(required=True)
)
async def delete_llm_tool():
    """
    删除LLM工具
    """
    try:
        tool_id = g.validated_data['toolId']
        result = service_container.llm_tool_service().delete_llm_tool(tool_id)

        if result:
            result = ResultVo(success=True, result="删除成功")
            return jsonify(success(result).to_dict())
        else:
            result = ResultVo(success=False, result="未找到对应记录")
            return jsonify(success(result).to_dict())
    except Exception as e:
        return jsonify(failure_with_ex(e).to_dict())


@llm_tool_api.route('/getById', methods=['GET'])
@validate_query_params(
    toolId=fields.Int(required=True)
)
async def get_llm_tool():
    """
    根据ID获取LLM工具
    """
    try:
        tool_id = g.validated_data['toolId']
        llm_tool = service_container.llm_tool_service().get_llm_tool_by_id(tool_id)

        if not llm_tool:
            result = ResultVo(success=False, result="未找到对应记录")
            return jsonify(success(result).to_dict())

        # 转换为LLMToolVO对象
        llm_tool_vo = LLMToolVO(
            id=llm_tool.id,
            name=llm_tool.name,
            description=llm_tool.description,
            args_dict=llm_tool.args_dict,
            tool_type=llm_tool.tool_type,
            content=llm_tool.content,
            request_handle_script=llm_tool.request_handle_script,
            response_handle_script=llm_tool.response_handle_script,
            gmt_create=format_datatime(llm_tool.gmt_create) if llm_tool.gmt_create else None,
            gmt_modified=format_datatime(llm_tool.gmt_modified) if llm_tool.gmt_modified else None
        )

        result = ResultVo(success=True, result=llm_tool_vo)
        return jsonify(success(result).to_dict())
    except Exception as e:
        return jsonify(failure_with_ex(e).to_dict())


@llm_tool_api.route('/list', methods=['GET'])
@validate_query_params(
    name=fields.Str(required=False),
    toolType=fields.Str(required=False),
    page=fields.Int(required=False, missing=1),
    pageSize=fields.Int(required=False, missing=20)
)
async def list_llm_tools():
    """
    列出符合条件的LLM工具
    支持根据name、tool_type查询
    """
    try:
        # 获取查询参数
        name = g.validated_data.get('name')
        tool_type = g.validated_data.get('toolType')
        page = g.validated_data['page']
        page_size = g.validated_data['pageSize']
        page_size = min(page_size, 100)  # 限制最大页面大小

        # 查询数据
        llm_tools = service_container.llm_tool_service().list_llm_tools(
            name=name,
            tool_type=tool_type,
            page=page,
            page_size=page_size
        )

        # 转换为LLMToolVO列表
        llm_tool_vos = []
        for llm_tool in llm_tools:
            llm_tool_vo = LLMToolVO(
                id=llm_tool.id,
                name=llm_tool.name,
                description=llm_tool.description,
                args_dict=llm_tool.args_dict,
                tool_type=llm_tool.tool_type,
                content=llm_tool.content,
                request_handle_script=llm_tool.request_handle_script,
                response_handle_script=llm_tool.response_handle_script,
                gmt_create=format_datatime(llm_tool.gmt_create) if llm_tool.gmt_create else None,
                gmt_modified=format_datatime(llm_tool.gmt_modified) if llm_tool.gmt_modified else None
            )
            llm_tool_vos.append(llm_tool_vo.to_dict())

        # 使用PageResultVO封装分页数据
        page_result = PageResultVO[LLMToolVO](
            success=True,
            list=llm_tool_vos,
            pagination=Page(
                page=page,
                page_size=page_size,
                total=len(llm_tool_vos)  # 注意：实际项目中应该返回总记录数
            )
        )

        return jsonify(success(page_result).to_dict())
    except Exception as e:
        return jsonify(failure_with_ex(e).to_dict())


@llm_tool_api.route('/listByAgentId', methods=['GET'])
@validate_query_params(
    agentId=fields.Int(required=True)
)
async def list_llm_tools_by_agent_id():
    """
    根据Agent ID列出关联的LLM工具
    """
    try:
        # 获取查询参数
        agent_id = g.validated_data['agentId']

        # 查询数据
        llm_tools = service_container.llm_tool_service().get_llm_tools_by_agent_id(agent_id)

        # 转换为LLMToolVO列表
        llm_tool_vos = []
        for llm_tool in llm_tools:
            llm_tool_vo = LLMToolVO(
                id=llm_tool.id,
                name=llm_tool.name,
                description=llm_tool.description,
                args_dict=llm_tool.args_dict,
                tool_type=llm_tool.tool_type,
                content=llm_tool.content,
                request_handle_script=llm_tool.request_handle_script,
                response_handle_script=llm_tool.response_handle_script,
                gmt_create=format_datatime(llm_tool.gmt_create) if llm_tool.gmt_create else None,
                gmt_modified=format_datatime(llm_tool.gmt_modified) if llm_tool.gmt_modified else None
            )
            llm_tool_vos.append(llm_tool_vo.to_dict())

        result = ResultVo(success=True, result=llm_tool_vos)
        return jsonify(success(result).to_dict())
    except Exception as e:
        return jsonify(failure_with_ex(e).to_dict())