import httpx
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Agendamento, Cliente
from app.database import get_db

# CONFIGURAÇÕES DA API (Exemplo usando Evolution API ou similar)
# Se for rodar localmente para teste, use http://localhost:8080
# Se subir uma instância free no Render/Railway, use a URL dela.
API_URL = "http://localhost:8080"
API_KEY = "sua_api_key_aqui"
INSTANCE_NAME = "barbearia_instance"


async def enviar_mensagem_whatsapp(telefone: str, mensagem: str):
    """Envia mensagem via API externa."""
    # Limpa o telefone
    tel_limpo = "".join(filter(str.isdigit, telefone))
    if not tel_limpo.startswith("55"):
        tel_limpo = "55" + tel_limpo.lstrip("0")

    payload = {"number": tel_limpo, "textMessage": {"text": mensagem}, "delay": 1200}

    headers = {"apikey": API_KEY}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/message/sendText/{INSTANCE_NAME}",
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            if response.status_code == 200:
                print(f"✅ Mensagem enviada para {telefone}")
                return True
            else:
                print(f"❌ Erro ao enviar para {telefone}: {response.text}")
                return False
    except Exception as e:
        print(f"❌ Exceção no envio: {e}")
        return False


async def verificar_e_enviar_lembretes(db: AsyncSession):
    """
    Roda periodicamente para verificar agendamentos do dia seguinte e do dia atual.
    Regras:
    1. Lembrete de Confirmação (Dia anterior ou 24h antes) - Opcional
    2. Lembrete de 2 Horas antes
    3. Lembrete de 30 Minutos antes
    """
    agora = datetime.now()

    # Busca agendamentos futuros não cancelados
    stmt = (
        select(Agendamento)
        .options(
            # Precisa carregar cliente e barbeiro
        )
        .where(
            Agendamento.data >= agora.date(),
            Agendamento.pago == False,  # Ou True, dependendo da sua regra
        )
    )

    # Nota: Em produção, você precisaria fazer o join correto ou usar selectinload
    # Aqui simplifiquei para focar na lógica de tempo

    # Vamos buscar todos os agendamentos de hoje e amanhã para filtrar em Python (mais fácil para começar)
    # Em produção com milhares de registros, faça o filtro direto no SQL

    stmt_full = select(Agendamento).where(
        Agendamento.data.between(agora.date(), agora.date() + timedelta(days=1))
    )
    # Adicione loads aqui: .options(selectinload(Agendamento.cliente))

    res = await db.execute(stmt_full)
    agendamentos = res.scalars().all()

    for agd in agendamentos:
        if not agd.cliente:
            continue  # Segurança

        data_hora_agendamento = datetime.combine(agd.data, agd.hora)
        diferenca = data_hora_agendamento - agora

        minutos_restantes = diferenca.total_seconds() / 60

        # Lógica de Disparo
        # Evitar reenvio: Você precisaria de um campo no banco 'lembrete_2h_enviado', 'lembrete_30m_enviado'
        # Vou simular a verificação apenas pelo tempo agora

        mensagem = ""
        enviar = False

        # 1. Lembrete de 2 Horas (Entre 2h e 2h05min)
        if 115 <= minutos_restantes <= 125:
            # if not agd.lembrete_2h_enviado: (Adicionar esse campo no modelo depois)
            mensagem = (
                f"👋 Olá, *{agd.cliente.nome}*!\n\n"
                f"Passando para lembrar do seu horário na Barbearia hoje às *{agd.hora.strftime('%H:%M')}*.\n"
                f"Barbeiro: {agd.barbeiro.nome if agd.barbeiro else 'Equipe'}\n\n"
                f"Te esperamos! 💈✂️"
            )
            enviar = True
            # agd.lembrete_2h_enviado = True

        # 2. Lembrete de 30 Minutos (Entre 30min e 35min)
        elif 25 <= minutos_restantes <= 35:
            # if not agd.lembrete_30m_enviado:
            mensagem = (
                f"⏰ *Falta pouco!* \n\n"
                f"Seu horário é daqui a 30 minutos ({agd.hora.strftime('%H:%M')}).\n"
                f"Já estamos te esperando, {agd.cliente.nome}!\n\n"
                f"Qualquer imprevisto, nos avise. 💈"
            )
            enviar = True
            # agd.lembrete_30m_enviado = True

        if enviar and mensagem:
            await enviar_mensagem_whatsapp(agd.cliente.telefone, mensagem)
            # await db.commit() # Commitar os flags de enviado
