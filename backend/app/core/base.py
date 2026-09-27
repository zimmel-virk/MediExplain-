"""SQLAlchemy declarative base isolated from runtime engine creation."""
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
