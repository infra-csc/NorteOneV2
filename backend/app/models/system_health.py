from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from ..core.database import Base


class SystemHealthEvent(Base):
    __tablename__ = "system_health_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)
    message = Column(Text, nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "event_type": self.event_type,
            "severity": self.severity,
            "message": self.message,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SystemAlertConfig(Base):
    __tablename__ = "system_alert_config"

    id = Column(Integer, primary_key=True, default=1)
    email_enabled = Column(Boolean, default=False)
    email_recipients = Column(Text, nullable=True)
    email_from = Column(String(255), nullable=True)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String(255), nullable=True)
    smtp_password = Column(Text, nullable=True)
    slack_enabled = Column(Boolean, default=False)
    slack_webhook_url = Column(Text, nullable=True)
    min_severity = Column(String(20), default="HIGH")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        masked_webhook = None
        if self.slack_webhook_url:
            url = self.slack_webhook_url
            masked_webhook = url[:30] + "***" if len(url) > 30 else "***"
        return {
            "email_enabled": self.email_enabled,
            "email_recipients": self.email_recipients,
            "email_from": self.email_from,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_user": self.smtp_user,
            "smtp_password": "***" if self.smtp_password else None,
            "slack_enabled": self.slack_enabled,
            "slack_webhook_url": masked_webhook,
            "min_severity": self.min_severity,
        }
