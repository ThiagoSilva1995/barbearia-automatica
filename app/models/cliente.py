from sqlalchemy import Column, Integer, String, Date, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
from app.utils.phone_utils import format_phone_for_display  # ← NOVO IMPORT


class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    telefone = Column(String(15), nullable=False)  # Armazena: 5573999999999
    data_nascimento = Column(Date, nullable=False)
    parabens_enviado = Column(Boolean, default=False)
    agendamentos = relationship(
        "Agendamento", back_populates="cliente", cascade="all, delete-orphan"
    )

    # ← NOVA PROPERTY para exibição formatada
    @property
    def telefone_formatado(self) -> str:
        """Retorna o telefone formatado para exibição: +55 (73) 99999-9999"""
        return format_phone_for_display(self.telefone)
