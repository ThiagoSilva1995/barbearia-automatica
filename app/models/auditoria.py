from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base


class AuditoriaAgendamento(Base):
    """Registra todas as operações críticas em agendamentos"""
    __tablename__ = "auditoria_agendamentos"
    
    id = Column(Integer, primary_key=True, index=True)
    agendamento_id = Column(Integer, nullable=True, index=True)
    acao = Column(String(50), nullable=False, index=True)  # criado, editado, cancelado, removido
    usuario_tipo = Column(String(20), nullable=False)  # 'admin', 'cliente', 'sistema'
    usuario_id = Column(Integer, nullable=True)
    usuario_nome = Column(String(255), nullable=True)
    
    # Dados do agendamento (snapshot)
    cliente_nome = Column(String(255), nullable=True)
    barbeiro_nome = Column(String(255), nullable=True)
    data_agendamento = Column(String(20), nullable=True)
    hora_agendamento = Column(String(10), nullable=True)
    servicos = Column(JSON, nullable=True)
    
    # Detalhes adicionais
    detalhes = Column(JSON, nullable=True)
    ip_origem = Column(String(50), nullable=True)
    
    # Timestamp em horário de Brasília
    criada_em = Column(DateTime(timezone=True), 
                       server_default=func.now(),
                       nullable=False,
                       index=True)
    
    def __repr__(self):
        return f"<Auditoria {self.acao} agendamento={self.agendamento_id}>"
