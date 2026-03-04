from sqlalchemy import Column, Integer, String, DateTime, Text, UniqueConstraint
from sqlalchemy.sql import func
from ..core.database import Base


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    id = Column(Integer, primary_key=True, index=True)
    cache_name = Column(String(100), nullable=False, index=True)
    cache_key = Column(String(255), nullable=False, index=True)
    data = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('cache_name', 'cache_key', name='uq_cache_name_key'),
    )
