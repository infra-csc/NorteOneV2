from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base

class Usuario(Base):
    __tablename__ = "dim_usuario"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    nome = Column(String(100), nullable=False)
    # Nullable: contas provisionadas via Microsoft SSO não têm senha local
    # (single sign-on puro). Continua obrigatória na prática para contas locais
    # (break-glass) — a rota de criação local sempre gera o hash.
    senha_hash = Column(String(255), nullable=True)
    # Microsoft Entra ID (Azure AD) object id — identifica univocamente a conta
    # no diretório. Preenchido em contas SSO; NULL em contas locais.
    ms_oid = Column(String(100), nullable=True, unique=True, index=True)
    # Origem/forma de autenticação: 'local' (e-mail+senha) ou 'microsoft' (SSO).
    auth_provider = Column(String(20), nullable=False, default="local")
    # Break-glass / acesso de emergência: quando True, a conta pode autenticar
    # por SENHA local MESMO sendo gerenciada pelo diretório (auth_provider=
    # 'microsoft'), e a sincronização NUNCA zera a senha nem a desativa. Permite
    # login duplo (Microsoft + emergência) para administradores de contingência.
    permite_login_local = Column(Boolean, nullable=False, default=False)
    # Último instante em que a conta foi reconciliada com o diretório Microsoft.
    ms_synced_at = Column(DateTime, nullable=True)
    perfil_acesso_id = Column(Integer, ForeignKey("perfil_acesso.id"), nullable=True, index=True)
    centro_custo_id = Column(Integer, ForeignKey("dim_centro_custo.id"), index=True)
    ativo = Column(Boolean, default=True, index=True)
    recebe_alertas_corte = Column(Boolean, default=False)
    recebe_insights_nori = Column(Boolean, default=False)
    foto_perfil = Column(String(500), nullable=True)
    foto_perfil_data = Column(LargeBinary, nullable=True)
    foto_perfil_mime = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=func.now())
    last_activity = Column(DateTime, nullable=True, index=True)
    
    centro_custo = relationship("DimCentroCusto")
    perfil_acesso_rel = relationship("PerfilAcesso", back_populates="usuarios")
