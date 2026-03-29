import asyncio
import httpx
from datetime import datetime, timedelta, time
import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import Agendamento, Cliente
from app.services.whatsapp_service import (
    enviar_mensagem_automatica,
    gerar_mensagem_aniversario,
)

tz_br = pytz.timezone("America/Sao_Paulo")

# Configurações da API (Devem bater com seu docker-compose)
API_URL = "http://localhost:8080"
API_KEY = "sua_chave_secreta_123"
INSTANCE_NAME = "barbearia"


async def verificar_e_enviar_aniversariantes(db: AsyncSession):
    """
    Verifica aniversariantes e envia APENAS UMA VEZ no dia, às 09:00 ou depois.
    """
    agora = datetime.now(tz_br)
    hoje = agora.date()
    hora_atual = agora.time()

    HORA_ENVIO = time(9, 0)

    # Se ainda não são 9h, sai da função
    if hora_atual < HORA_ENVIO:
        return

    # Reset automático no dia 1º de Janeiro (Opcional, mas recomendado)
    if hoje.day == 1 and hoje.month == 1:
        from sqlalchemy import update

        await db.execute(update(Cliente).values(parabens_enviado=False))
        await db.commit()
        print("🔄 Campos de aniversário resetados para o novo ano.")

    # Busca clientes que fazem aniversário hoje E ainda não receberam o parabéns
    stmt = select(Cliente).where(
        Cliente.data_nascimento != None, Cliente.parabens_enviado == False
    )
    result = await db.execute(stmt)
    clientes = result.scalars().all()

    aniversariantes_do_dia = [
        c
        for c in clientes
        if c.data_nascimento.day == hoje.day and c.data_nascimento.month == hoje.month
    ]

    if not aniversariantes_do_dia:
        return

    print(f"🎂 Encontrados {len(aniversariantes_do_dia)} aniversariantes para hoje.")

    for cliente in aniversariantes_do_dia:
        try:
            msg = gerar_mensagem_aniversario(cliente)
            sucesso = await enviar_mensagem_automatica(cliente.telefone, msg)

            if sucesso:
                print(f"✅ Parabéns enviado para {cliente.nome}")
                cliente.parabens_enviado = True
                await db.commit()
            else:
                print(f"❌ Falha ao enviar para {cliente.nome}")
        except Exception as e:
            print(f"❌ Erro no processo de {cliente.nome}: {e}")
            await db.rollback()


async def verificar_e_enviar_lembretes_agendamento(db: AsyncSession):
    """
    Verifica agendamentos e envia lembretes de 2h e 30min.
    Nota: Como não temos colunas 'lembrete_enviado' no banco ainda,
    a lógica abaixo usa uma janela de tempo estreita para evitar repetição imediata.
    Para produção robusta, recomenda-se adicionar colunas 'lembrete_2h_enviado' no modelo Agendamento.
    """
    agora = datetime.now(tz_br)
    hoje = agora.date()
    amanhã = hoje + timedelta(days=1)

    # Busca agendamentos de hoje e amanhã
    stmt = (
        select(Agendamento)
        .options(selectinload(Agendamento.cliente), selectinload(Agendamento.barbeiro))
        .where(Agendamento.data.between(hoje, amanhã))
    )
    result = await db.execute(stmt)
    agendamentos = result.scalars().all()

    for agd in agendamentos:
        if (
            not agd.cliente or agd.pago == False
        ):  # Ajuste a regra de 'pago' conforme necessário
            continue

        # Combina data e hora do agendamento
        dt_agendamento = tz_br.localize(datetime.combine(agd.data, agd.hora))
        diferenca = dt_agendamento - agora
        minutos_restantes = diferenca.total_seconds() / 60

        if minutos_restantes < 0:
            continue  # Já passou

        mensagem = ""
        enviar = False

        # Janela de 2 horas (entre 1h55min e 2h05min)
        if 115 <= minutos_restantes <= 125:
            # Aqui idealmente checaria: if not agd.lembrete_2h_enviado
            mensagem = (
                f"👋 Olá, *{agd.cliente.nome}*!\n\n"
                f"Lembrete do seu horário hoje às *{agd.hora.strftime('%H:%M')}*.\n"
                f"Barbeiro: {agd.barbeiro.nome}\n\n"
                f"Te esperamos! 💈"
            )
            enviar = True
            # agd.lembrete_2h_enviado = True

        # Janela de 30 min (entre 25min e 35min)
        elif 25 <= minutos_restantes <= 35:
            # if not agd.lembrete_30m_enviado
            mensagem = (
                f"⏰ *Falta pouco!* \n\n"
                f"Seu horário é daqui a 30 min ({agd.hora.strftime('%H:%M')}).\n"
                f"Já estamos te esperando, {agd.cliente.nome}!\n\n"
                f"Qualquer imprevisto, nos avise. 💈"
            )
            enviar = True
            # agd.lembrete_30m_enviado = True

        if enviar and mensagem:
            await enviar_mensagem_automatica(agd.cliente.telefone, mensagem)
            # await db.commit() # Commitar flags se existirem


async def loop_de_verificacao(db_session_maker):
    """Loop infinito que roda a cada 1 minuto para maior precisão."""
    print("🤖 Robô de Lembretes e Aniversários Iniciado...")
    while True:
        try:
            async with db_session_maker() as db:
                await verificar_e_enviar_aniversariantes(db)
                await verificar_e_enviar_lembretes_agendamento(db)
        except Exception as e:
            print(f"❌ Erro no loop de fundo: {e}")

        # Espera 60 segundos antes de verificar de novo
        await asyncio.sleep(60)
