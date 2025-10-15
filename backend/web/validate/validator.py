from functools import wraps
from quart import request, g
from flask_marshmallow import Schema
from marshmallow import ValidationError
from model.response import failure_with_ex
import asyncio

def validate_query_params(**field_definitions):
    def decorator(func):
        # 根据原函数决定返回同步还是异步包装器
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    schema_cls = Schema.from_dict(field_definitions)
                    query_params = dict(request.args)
                    validated_data = schema_cls().load(query_params)
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
                    query_params = dict(request.args)
                    validated_data = schema_cls().load(query_params)
                    g.validated_data = validated_data
                    return func(*args, **kwargs)
                except ValidationError as err:
                    return failure_with_ex(err)
            return sync_wrapper
    return decorator
