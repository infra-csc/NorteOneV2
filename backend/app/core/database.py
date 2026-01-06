from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

engine = create_engine(settings.DATABASE_URL) if settings.DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()

def get_db():
    if SessionLocal is None:
        raise Exception("DATABASE_URL not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

engine_ativo = None
SessionLocalAtivo = None

engine_magento = None
SessionLocalMagento = None

def init_mysql_connections():
    global engine_ativo, SessionLocalAtivo, engine_magento, SessionLocalMagento
    
    if settings.MYSQL_ATIVO_PASSWORD and settings.MYSQL_ATIVO_DATABASE:
        engine_ativo = create_engine(
            settings.MYSQL_ATIVO_URL,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        SessionLocalAtivo = sessionmaker(autocommit=False, autoflush=False, bind=engine_ativo)
    
    if settings.MYSQL_MAGENTO_PASSWORD and settings.MYSQL_MAGENTO_DATABASE:
        engine_magento = create_engine(
            settings.MYSQL_MAGENTO_URL,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        SessionLocalMagento = sessionmaker(autocommit=False, autoflush=False, bind=engine_magento)

def get_db_ativo():
    if SessionLocalAtivo is None:
        raise Exception("MySQL Ativo connection not configured. Check MYSQL_ATIVO_PASSWORD and MYSQL_ATIVO_DATABASE.")
    db = SessionLocalAtivo()
    try:
        yield db
    finally:
        db.close()

def get_db_magento():
    if SessionLocalMagento is None:
        raise Exception("MySQL Magento connection not configured. Check MYSQL_MAGENTO_PASSWORD and MYSQL_MAGENTO_DATABASE.")
    db = SessionLocalMagento()
    try:
        yield db
    finally:
        db.close()
