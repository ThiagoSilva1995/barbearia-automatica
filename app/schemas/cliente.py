from pydantic import BaseModel, Field
from datetime import date
from typing import Optional


class ClienteBase(BaseModel):
    nome: str = Field(..., min_length=3, description="Nome completo do cliente")
    telefone: str = Field(..., pattern=r"^\d{10,15}$", description="Número de telefone (10-15 dígitos)")
    data_nascimento: date = Field(..., description="Data de nascimento no formato YYYY-MM-DD")


class ClienteCreate(ClienteBase):
    """Schema para criação de novo cliente"""
    pass


class ClienteUpdate(BaseModel):
    """Schema para atualização parcial de cliente (todos os campos opcionais)"""
    nome: Optional[str] = Field(None, min_length=3, description="Nome completo do cliente")
    telefone: Optional[str] = Field(None, pattern=r"^\d{10,15}$", description="Número de telefone (10-15 dígitos)")
    data_nascimento: Optional[date] = Field(None, description="Data de nascimento no formato YYYY-MM-DD")


class ClienteResponse(ClienteBase):
    """Schema de resposta com dados completos do cliente"""
    id: int = Field(..., description="ID único do cliente")
    parabens_enviado: bool = Field(..., description="Flag indicando se parabéns já foram enviados")

    class Config:
        from_attributes = True
