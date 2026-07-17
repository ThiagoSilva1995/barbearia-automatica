from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Notificacao(Base):
    """Modelo para notificações in-app do sistema"""
    __tablename__ = "notificacoes"

    id = Column(Integer, primary_key=True, index=True)
    
    # Tipo de notificação
    tipo = Column(String(50), nullable=False)  # agendamento, lembrete, aniversario, fila, sistema
    
    # Título e mensagem
    titulo = Column(String(200), nullable=False)
    mensagem = Column(Text, nullable=True)
    
    # Ícone (emoji)
    icone = Column(String(10), default="🔔")
    
    # Cor do badge (para diferentes tipos)
    cor = Column(String(20), default="red")  # red, green, blue, orange, purple
    
    # Link para redirecionamento (URL relativa)
    link = Column(String(500), nullable=True)
    
    # ID do agendamento relacionado (para redirecionamento inteligente)
    # ondelete="CASCADE" garante que a notificação seja excluída automaticamente se o agendamento for deletado
    agendamento_id = Column(Integer, ForeignKey("agendamentos.id", ondelete="CASCADE"), nullable=True)
    
    # Relacionamento inverso para cascade delete funcionar corretamente na ORM
    agendamento = relationship("Agendamento", back_populates="notificacoes")
    
    # Data do agendamento (para redirecionamento inteligente)
    data_agendamento = Column(String(10), nullable=True)  # Formato: YYYY-MM-DD
    
    # Status de leitura
    lida = Column(Boolean, default=False)
    
    # Timestamps
    criada_em = Column(DateTime(timezone=True), server_default=func.now())
    lida_em = Column(DateTime(timezone=True), nullable=True)
    
    # Dados extras em JSON (opcional)
    dados_extra = Column(Text, nullable=True)  # JSON string com dados adicionais
    
    def __repr__(self):
        return f"<Notificacao(id={self.id}, tipo='{self.tipo}', titulo='{self.titulo}', lida={self.lida})>"
