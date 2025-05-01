from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .__all_models import Base

SQLITE_DB_NAME = 'db/shop.db'


def global_init(db_file: str = SQLITE_DB_NAME):
    engine = create_engine(f'sqlite:///{db_file}', echo=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return factory


Session = global_init()
