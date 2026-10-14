from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickpick.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
