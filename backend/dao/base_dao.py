from sqlalchemy.orm import sessionmaker

class BaseDAO:

    def __init__(self, engine):
        self.engine = engine
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_session(self):
        return self.Session()

    def execute_in_session(self, func):
        with self._get_session() as session:
            try:
                result = func(session)
                session.commit()
                return result
            except Exception as e:
                session.rollback()
                raise e
