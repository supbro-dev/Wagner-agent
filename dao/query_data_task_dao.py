from entity.query_data_task_entity import QueryDataTaskEntity


def find_by_name(business_key, name) -> QueryDataTaskEntity:
    entity = QueryDataTaskEntity.query.filter_by(business_key = business_key, name = name).one_or_none()
    return entity

def find_by_id(id) -> QueryDataTaskEntity:
    entity = QueryDataTaskEntity.query.filter_by(id=id).one_or_none()
    return entity