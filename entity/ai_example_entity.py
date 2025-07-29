from flask_sqlalchemy import SQLAlchemy

from app import db


class AiExampleEntity(db.Model):
    __tablename__ = 'ai_example'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    gmt_create = db.Column(db.DATETIME)
    gmt_modified = db.Column(db.DATETIME)
    key = db.Column(db.String)
    human_message = db.Column(db.String)
    tool_message = db.Column(db.String)
    ai_message = db.Column(db.String)
    sort_index = db.Column(db.Integer)
