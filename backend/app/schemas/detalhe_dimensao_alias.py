from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import re

DIMENSOES_VALIDAS = ["kit", "modalidade", "pelotao", "tamanho_camiseta", "produtos"]


class DetalheDimensaoAliasBase(BaseModel):
    dimensao: str
    pattern: str
    substituicao: str
    is_regex: bool = False
    ordem: int = 0
    ativo: bool = True
    descricao: Optional[str] = None

    @field_validator("dimensao")
    @classmethod
    def dimensao_valida(cls, v: str) -> str:
        if v not in DIMENSOES_VALIDAS:
            raise ValueError(f"dimensao deve ser um de: {DIMENSOES_VALIDAS}")
        return v

    @field_validator("pattern")
    @classmethod
    def pattern_nao_vazio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("pattern não pode ser vazio")
        return v

    @field_validator("substituicao")
    @classmethod
    def substituicao_nao_vazia(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("substituicao não pode ser vazia")
        return v


class DetalheDimensaoAliasCreate(DetalheDimensaoAliasBase):
    pass


class DetalheDimensaoAliasUpdate(BaseModel):
    dimensao: Optional[str] = None
    pattern: Optional[str] = None
    substituicao: Optional[str] = None
    is_regex: Optional[bool] = None
    ordem: Optional[int] = None
    ativo: Optional[bool] = None
    descricao: Optional[str] = None

    @field_validator("dimensao")
    @classmethod
    def dimensao_valida(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in DIMENSOES_VALIDAS:
            raise ValueError(f"dimensao deve ser um de: {DIMENSOES_VALIDAS}")
        return v


class DetalheDimensaoAliasResponse(DetalheDimensaoAliasBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TestPatternRequest(BaseModel):
    pattern: str
    substituicao: str
    is_regex: bool = False
    sample: str


class TestPatternResponse(BaseModel):
    original: str
    resultado: str
    casou: bool
    erro: Optional[str] = None
