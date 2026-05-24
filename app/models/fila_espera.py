# app/models/fila_espera.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from app.database import Base


class FilaEspera(Base):
    """
    Gerencia fila de espera para horários vagos com efeito cascata
    """

    __tablename__ = "fila_espera"

    id = Column(Integer, primary_key=True, index=True)

    # Horário vago que está sendo oferecido
    horario_vago = Column(DateTime, nullable=False)

    # Cliente atual que tem o horário e quer mudar
    cliente_atual_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    cliente_atual = relationship("Cliente", foreign_keys=[cliente_atual_id])

    # Próximo cliente na fila que receberá a oferta
    proximo_cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    proximo_cliente = relationship("Cliente", foreign_keys=[proximo_cliente_id])

    # Status da oferta
    status = Column(
        String(50), default="aguardando"
    )  # aguardando, aceita, recusa, expirado

    # Tempo limite para resposta (10 minutos)
    criado_em = Column(DateTime, default=datetime.now)
    expira_em = Column(DateTime, nullable=True)

    # Tentativa atual na cascata
    tentativa = Column(Integer, default=1)

    # Horário novo que o cliente atual quer
    horario_novo = Column(DateTime, nullable=True)

    # Mensagem já enviada
    mensagem_enviada = Column(Boolean, default=False)
