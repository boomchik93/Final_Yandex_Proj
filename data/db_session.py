from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .__all_models import Base
from sqlalchemy.types import DateTime
import pytz
from datetime import datetime

DATABASE_URL = "sqlite:///db/shop.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def moscow_datetime():
    return datetime.now(pytz.timezone('Europe/Moscow'))


def setup_sqlite():
    engine = create_engine(DATABASE_URL)

    def moscow_date_processor(dt):
        return dt.astimezone(pytz.timezone('Europe/Moscow')).isoformat()

    DateTime.ResultProcessor = type(
        'DateTimeMoscow',
        (DateTime.ResultProcessor,),
        {'process': lambda self, value: moscow_date_processor(value)}
    )


def global_init(db_file: str = 'db/shop.db'):
    engine = create_engine(f'sqlite:///{db_file}', echo=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


Session = global_init()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
