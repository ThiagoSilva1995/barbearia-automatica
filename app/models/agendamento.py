# app/models/agendamento.py
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    Date,
    Time,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database import Base
from .servico import agendamento_servico
from .produto import agendamento_produto


class Agendamento(Base):
    __tablename__ = "agendamentos"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    barbeiro_id = Column(Integer, ForeignKey("barbeiros.id"), nullable=False)
    data = Column(Date, nullable=False)
    hora = Column(Time, nullable=False)
    pago = Column(Boolean, default=False)
    is_confirmed = Column(Boolean, default=False)

    # ✅ NOVO CAMPO: Duração em minutos (padrão: 30)
    # Necessário para cálculo de sobreposição de horários
    duracao_minutos = Column(Integer, default=30, nullable=False)

    cliente = relationship("Cliente", back_populates="agendamentos")
    barbeiro = relationship("Barbeiro", back_populates="agendamentos")
    servicos = relationship(
        "Servico", secondary=agendamento_servico, back_populates="agendamentos"
    )
    produtos = relationship(
        "Produto", secondary=agendamento_produto, back_populates="agendamentos"
    )

    __table_args__ = (
        UniqueConstraint("barbeiro_id", "data", "hora", name="uq_barbeiro_data_hora"),
    )
