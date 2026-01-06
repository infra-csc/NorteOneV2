import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    SECRET_KEY: str = os.getenv("SESSION_SECRET", "default-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    
    MYSQL_ATIVO_HOST: str = "o2-db-ativos-2-aurora-cluster.cluster-ro-cgqle4cw3o4s.us-east-1.rds.amazonaws.com"
    MYSQL_ATIVO_PORT: int = 3306
    MYSQL_ATIVO_USER: str = "user-matheus"
    MYSQL_ATIVO_PASSWORD: str = os.getenv("MYSQL_ATIVO_PASSWORD", "")
    MYSQL_ATIVO_DATABASE: str = os.getenv("MYSQL_ATIVO_DATABASE", "")
    
    MYSQL_MAGENTO_HOST: str = "prod-magento2-runningland-db-ro.cxogiuqtlrun.us-east-2.rds.amazonaws.com"
    MYSQL_MAGENTO_PORT: int = 3306
    MYSQL_MAGENTO_USER: str = "leonardo.urbano"
    MYSQL_MAGENTO_PASSWORD: str = os.getenv("MYSQL_MAGENTO_PASSWORD", "")
    MYSQL_MAGENTO_DATABASE: str = os.getenv("MYSQL_MAGENTO_DATABASE", "")
    
    @property
    def MYSQL_ATIVO_URL(self) -> str:
        return f"mysql+pymysql://{self.MYSQL_ATIVO_USER}:{self.MYSQL_ATIVO_PASSWORD}@{self.MYSQL_ATIVO_HOST}:{self.MYSQL_ATIVO_PORT}/{self.MYSQL_ATIVO_DATABASE}"
    
    @property
    def MYSQL_MAGENTO_URL(self) -> str:
        return f"mysql+pymysql://{self.MYSQL_MAGENTO_USER}:{self.MYSQL_MAGENTO_PASSWORD}@{self.MYSQL_MAGENTO_HOST}:{self.MYSQL_MAGENTO_PORT}/{self.MYSQL_MAGENTO_DATABASE}"
    
    class Config:
        env_file = ".env"

settings = Settings()
