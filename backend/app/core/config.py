import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    SECRET_KEY: str = os.getenv("SESSION_SECRET", "")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5000,http://localhost:5173")
    
    # SSH Tunnel Configuration
    SSH_HOST: str = os.getenv("SSH_HOST", "")
    SSH_PORT: int = int(os.getenv("SSH_PORT", "22"))
    SSH_USER: str = os.getenv("SSH_USER", "")
    SSH_PRIVATE_KEY: str = os.getenv("SSH_PRIVATE_KEY", "")
    # Pinned SSH server public key in known_hosts format: "<key-type> <base64-key>"
    # Example: "ssh-rsa AAAAB3NzaC1yc2EAAA..."
    # If unset the tunnel will refuse to connect (fail-closed — no MITM risk).
    SSH_HOST_KEY: str = os.getenv("SSH_HOST_KEY", "")
    
    # Database via SSH Tunnel
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "")
    
    MYSQL_ATIVO_HOST: str = os.getenv("MYSQL_ATIVO_HOST", "")
    MYSQL_ATIVO_PORT: int = 3306
    MYSQL_ATIVO_USER: str = os.getenv("MYSQL_ATIVO_USER", "")
    MYSQL_ATIVO_PASSWORD: str = os.getenv("MYSQL_ATIVO_PASSWORD", "")
    MYSQL_ATIVO_DATABASE: str = os.getenv("MYSQL_ATIVO_DATABASE", "")
    
    MYSQL_MAGENTO_HOST: str = os.getenv("MAGENTO_DB_HOST", "")
    MYSQL_MAGENTO_PORT: int = int(os.getenv("MAGENTO_DB_PORT", "3306"))
    MYSQL_MAGENTO_USER: str = os.getenv("MAGENTO_DB_USER", "")
    MYSQL_MAGENTO_PASSWORD: str = os.getenv("MAGENTO_DB_PASSWORD", "")
    MYSQL_MAGENTO_DATABASE: str = os.getenv("MAGENTO_DB_NAME", "")
    
    @property
    def MYSQL_ATIVO_URL(self) -> str:
        return f"mysql+pymysql://{self.MYSQL_ATIVO_USER}:{self.MYSQL_ATIVO_PASSWORD}@{self.MYSQL_ATIVO_HOST}:{self.MYSQL_ATIVO_PORT}/{self.MYSQL_ATIVO_DATABASE}"
    
    @property
    def MYSQL_MAGENTO_URL(self) -> str:
        return f"mysql+pymysql://{self.MYSQL_MAGENTO_USER}:{self.MYSQL_MAGENTO_PASSWORD}@{self.MYSQL_MAGENTO_HOST}:{self.MYSQL_MAGENTO_PORT}/{self.MYSQL_MAGENTO_DATABASE}"
    
    class Config:
        env_file = ".env"

settings = Settings()
