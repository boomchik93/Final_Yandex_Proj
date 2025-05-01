from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .__all_models import Base

DATABASE_URL = "sqlite:///db/shop.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
