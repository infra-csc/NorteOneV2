from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from ..core.database import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("dim_usuario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    jti = Column(String(36), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_user_sessions_user_expires", "user_id", "expires_at"),
    )
