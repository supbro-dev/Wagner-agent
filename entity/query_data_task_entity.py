from init import db


class QueryDataTaskEntity(db.Model):
    __tablename__ = 'query_data_task'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    business_key = db.Column(db.String)
    name = db.Column(db.String)
    task_detail = db.Column(db.String)

