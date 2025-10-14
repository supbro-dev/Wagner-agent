from functools import wraps

from flask import request
from flask_marshmallow import Schema
from marshmallow import ValidationError

from model.response import failure_with_ex

def validate_query_params(**field_definitions):
    """
    动态生成 Schema 的装饰器
    :param field_definitions: 字段定义，如 `businessKey=fields.Str(required=True)`
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                # 动态创建 Schema
                schema_cls = Schema.from_dict(field_definitions)
                validated_data = schema_cls().load(request.args.to_dict())
                request.validated_data = validated_data
                return func(*args, **kwargs)
            except ValidationError as err:
                return failure_with_ex(err)
        return wrapper
    return decorator
