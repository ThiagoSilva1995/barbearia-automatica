from pydantic import BaseModel, Field
from datetime import date, time
from typing import List, Optional


class AgendamentoBase(BaseModel):
    cliente_id: int = Field(..., description="ID do cliente")
    barbeiro_id: int = Field(..., description="ID do barbeiro")
    data: date = Field(..., description="Data do agendamento (YYYY-MM-DD)")
    hora: time = Field(..., description="Horário de início (HH:MM)")
    servico_ids: List[int] = Field(default=[], description="Lista de IDs dos serviços")
    produto_ids: List[int] = Field(default=[], description="Lista de IDs dos produtos (opcional)")


class AgendamentoCreate(AgendamentoBase):
    """Schema para criação de novo agendamento"""
    duracao_minutos: Optional[int] = Field(None, description="Duração total em minutos (calculado automaticamente se não fornecido)")


class AgendamentoUpdate(BaseModel):
    """Schema para atualização parcial de agendamento (todos os campos opcionais)"""
    cliente_id: Optional[int] = Field(None, description="ID do cliente")
    barbeiro_id: Optional[int] = Field(None, description="ID do barbeiro")
    data: Optional[date] = Field(None, description="Data do agendamento (YYYY-MM-DD)")
    hora: Optional[time] = Field(None, description="Horário de início (HH:MM)")
    servico_ids: Optional[List[int]] = Field(None, description="Lista de IDs dos serviços")
    produto_ids: Optional[List[int]] = Field(None, description="Lista de IDs dos produtos")
    pago: Optional[bool] = Field(None, description="Status de pagamento")
    duracao_minutos: Optional[int] = Field(None, description="Duração total em minutos")


class AgendamentoResponse(AgendamentoBase):
    """Schema de resposta com dados completos do agendamento"""
    id: int = Field(..., description="ID único do agendamento")
    pago: bool = Field(..., description="Status de pagamento")
    is_confirmed: bool = Field(..., description="Status de confirmação")
    duracao_minutos: Optional[int] = Field(None, description="Duração total em minutos")
    cliente: Optional[dict] = Field(None, description="Dados do cliente (se carregado)")
    barbeiro: Optional[dict] = Field(None, description="Dados do barbeiro (se carregado)")
    servicos: Optional[List[dict]] = Field(None, description="Lista de serviços (se carregado)")

    class Config:
        from_attributes = True
