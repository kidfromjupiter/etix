from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

DATABASE_URL = "sqlite:///./events.db"  # Use PostgreSQL in production

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, pool_size=20, max_overflow=30)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
