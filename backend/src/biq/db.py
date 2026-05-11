from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from biq.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)
