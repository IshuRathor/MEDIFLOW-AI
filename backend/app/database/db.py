import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


# Load environment variables
load_dotenv()

# PostgreSQL database URL
DATABASE_URL = os.getenv("DATABASE_URL")


# Create database engine
engine = create_engine(
    DATABASE_URL
)


# Create database session
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# Base class for SQLAlchemy models
Base = declarative_base()