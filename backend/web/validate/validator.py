from functools import wraps
from quart import request, g
from flask_marshmallow import Schema
from marshmallow import ValidationError
from model.response import failure_with_ex
import asyncio


def validate_request_params(param_source='query', **field_definitions):
    def decorator(func):
        # 根据原函数决定返回同步还是异步包装器
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    schema_cls = Schema.from_dict(field_definitions)
                    # 根据参数来源选择不同的数据源
                    if param_source == 'query':
                        params = dict(request.args)
                    elif param_source == 'form':
                        params = dict(request.form)
                    elif param_source == 'json':
                        params = await request.get_json() or {}
                    else:
                        params = dict(request.args)

                    validated_data = schema_cls().load(params)
                    g.validated_data = validated_data
                    return await func(*args, **kwargs)
                except ValidationError as err:
                    return failure_with_ex(err)

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    schema_cls = Schema.from_dict(field_definitions)
                    # 根据参数来源选择不同的数据源
                    if param_source == 'query':
                        params = dict(request.args)
                    elif param_source == 'form':
                        params = dict(request.form)
                    elif param_source == 'json':
                        params = request.get_json() or {}
                    else:
                        params = dict(request.args)

                    validated_data = schema_cls().load(params)
                    g.validated_data = validated_data
                    return func(*args, **kwargs)
                except ValidationError as err:
                    return failure_with_ex(err)

            return sync_wrapper

    return decorator


# 为了向后兼容，保留原来的装饰器
def validate_query_params(**field_definitions):
    return validate_request_params('query', **field_definitions)


# 新增处理POST JSON数据的装饰器
def validate_json_params(**field_definitions):
    return validate_request_params('json', **field_definitions)
