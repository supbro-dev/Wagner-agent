import json
import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool as create_tool
from pydantic import Field, create_model

from entity.llm_tool_entity import LLMToolType, LLMToolEntity
from model.llm_http_tool_content import LLMHTTPToolContent
from util.http_util import http_get, http_post


def create_llm_http_tool(lms_tool_entity: LLMToolEntity):
    """
    创建一个新的LLM HTTP工具

    参数:
        lms_tool_entity (LLMToolEntity): 工具实体对象

    返回:
        BaseTool: 构造好的LangChain工具对象
    """
    if lms_tool_entity.tool_type != LLMToolType.HTTP_TOOL:
        raise ValueError(f"工具类型不匹配，期望 HTTP_TOOL，实际得到 {lms_tool_entity.tool_type}")

    content = LLMHTTPToolContent.model_validate(json.loads(lms_tool_entity.content))
    http_method = content.method

    # 动态创建参数模型
    fields = {}
    args_dict = json.loads(lms_tool_entity.args_dict)
    for param in args_dict:
        desc = args_dict[param]
        fields[param] = (str, Field(description=desc))

    args_schema = create_model(f"{lms_tool_entity.name}Args", **fields)

    @create_tool(lms_tool_entity.name,
                 description=lms_tool_entity.description,
                 args_schema=args_schema)
    def tool_func(config: RunnableConfig, **tool_input):
        if http_method == "GET":
            res = http_get(content.url.format(**tool_input))
        elif http_method == "POST":
            res = http_post(content.url.format(**tool_input), json=tool_input)
        else:
            raise ValueError(f"不支持的HTTP方法：{http_method}")

        # 如果提供了处理脚本，则执行它
        if lms_tool_entity.response_handler_script:
            # 创建一个局部命名空间用于执行脚本
            local_namespace = {'res': res}

            try:
                # 执行预编译的脚本
                exec(lms_tool_entity.response_handler_script, {}, local_namespace)
                # 返回处理后的结果
                return local_namespace.get('result', res)
            except Exception as e:
                logging.error(f"执行处理脚本时出错: {e}")
                return res  # 出错时返回原始响应
        else:
            return res

    return tool_func