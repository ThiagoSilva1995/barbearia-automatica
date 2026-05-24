# app/models/configuracao.py
from sqlalchemy import Column, Integer, String, Text
from app.database import Base


class Configuracao(Base):
    __tablename__ = "configuracoes"
    id = Column(Integer, primary_key=True, index=True)

    # Dados da Barbearia
    nome_fantasia = Column(String, default="Barbearia do Thales")
    telefone_barbearia = Column(String, default="5573991449063")
    endereco = Column(String, default="Rua Exemplo, 123 - Centro")

    # Horários
    horario_inicio_manha = Column(String, default="08:30")
    horario_fim_manha = Column(String, default="11:00")
    horario_inicio_tarde = Column(String, default="14:00")
    horario_fim_tarde = Column(String, default="18:30")
    intervalo_minutos = Column(Integer, default=30)

    # Admin
    admin_nome = Column(String, default="Thales")
    admin_login = Column(String, default="admin")
    admin_senha = Column(String, default="admin123")  # ← NOVO CAMPO

    # Mensagens
    msg_aniversario = Column(Text, default="🎉 Feliz Aniversário!")
    msg_confirmacao = Column(Text, default="✅ Agendamento confirmado!")
