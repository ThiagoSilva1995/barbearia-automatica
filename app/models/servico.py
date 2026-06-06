# app/models/servico.py
from sqlalchemy import Column, Integer, String, Numeric, Table, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

# Tabela de associação Many-to-Many entre Agendamento e Servico
agendamento_servico = Table(
    "agendamento_servico",
    Base.metadata,
    Column("agendamento_id", Integer, ForeignKey("agendamentos.id"), primary_key=True),
    Column("servico_id", Integer, ForeignKey("servicos.id"), primary_key=True),
)


class Servico(Base):
    __tablename__ = "servicos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    descricao = Column(String, nullable=True)
    preco = Column(Numeric(10, 2), nullable=False)
    ativo = Column(Boolean, default=True)

    duracao_minutos = Column(Integer, default=10, nullable=False)

    # Relacionamento com Agendamentos
    agendamentos = relationship(
        "Agendamento", secondary=agendamento_servico, back_populates="servicos"
    )
