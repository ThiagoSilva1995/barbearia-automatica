# app/models/bloqueio.py
from sqlalchemy import Column, Integer, Date, String, Time
from app.database import Base


class BloqueioHorario(Base):
    __tablename__ = "bloqueios_horarios"

    id = Column(Integer, primary_key=True, index=True)
    data = Column(Date, nullable=False, unique=True)  # Data específica do bloqueio
    tipo = Column(String, default="FECHADO")  # FECHADO, SO_MANHA, SO_TARDE, PERSONALIZADO

    # Campos opcionais para personalização fina
    horario_inicio_manha = Column(Time, nullable=True)
    horario_fim_manha = Column(Time, nullable=True)
    horario_inicio_tarde = Column(Time, nullable=True)
    horario_fim_tarde = Column(Time, nullable=True)

    motivo = Column(String, nullable=True)
