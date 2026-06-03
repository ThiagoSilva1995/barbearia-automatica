# app/services/reminder_service.py
import asyncio
import httpx
from datetime import datetime, timedelta, time, date
import pytz
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import Agendamento, Cliente, Configuracao
from app.services.whatsapp_service import (
    enviar_mensagem_automatica,
    gerar_mensagem_aniversario,
)

tz_br = pytz.timezone("America/Sao_Paulo")

# Cache simples em memória para evitar envio duplicado no mesmo minuto
# Em produção, use Redis ou coluna no banco
enviados_recentemente = set()

HORA_INICIO_ANIVERSARIO = time(8, 0)
HORA_FIM_ANIVERSARIO = time(23, 0)
HORA_RESET_DIARIO = time(8, 0)


async def _reset_aniversariantes_diario(db: AsyncSession, hoje: date):
    """Reseta o flag parabens_enviado APENAS para aniversariantes de hoje."""
    stmt_check = select(Cliente).where(
        Cliente.data_nascimento != None,
        Cliente.parabens_enviado == True,
    )
    result = await db.execute(stmt_check)
    clientes_com_flag = result.scalars().all()

    aniversariantes_hoje_com_flag = [
        c
        for c in clientes_com_flag
        if c.data_nascimento.day == hoje.day and c.data_nascimento.month == hoje.month
    ]

    if aniversariantes_hoje_com_flag:
        for c in aniversariantes_hoje_com_flag:
            c.parabens_enviado = False
        await db.commit()
        print(f"🔄 Reset diário: {len(aniversariantes_hoje_com_flag)} flags resetadas.")


async def verificar_e_enviar_aniversariantes(db: AsyncSession):
    """Verifica aniversariantes e envia APENAS UMA VEZ no dia."""
    agora = datetime.now(tz_br)
    hoje = agora.date()
    hora_atual = agora.time()

    if hora_atual < HORA_INICIO_ANIVERSARIO or hora_atual >= HORA_FIM_ANIVERSARIO:
        return

    if hora_atual.hour == HORA_RESET_DIARIO.hour and hora_atual.minute < 5:
        await _reset_aniversariantes_diario(db, hoje)
        return

    stmt = select(Cliente).where(Cliente.data_nascimento != None, Cliente.parabens_enviado == False)
    result = await db.execute(stmt)
    clientes = result.scalars().all()

    aniversariantes_do_dia = [
        c
        for c in clientes
        if c.data_nascimento.day == hoje.day and c.data_nascimento.month == hoje.month
    ]

    if not aniversariantes_do_dia:
        return

    print(f"🎂 Encontrados {len(aniversariantes_do_dia)} aniversariantes.")

    for cliente in aniversariantes_do_dia:
        try:
            if (
                not cliente.telefone
                or len(str(cliente.telefone).replace(" ", "").replace("-", "")) < 10
            ):
                continue

            msg = gerar_mensagem_aniversario(cliente)
            sucesso = await enviar_mensagem_automatica(cliente.telefone, msg)

            if sucesso:
                print(f"✅ Parabéns enviado para {cliente.nome}")
                cliente.parabens_enviado = True
                await db.commit()
            else:
                print(f"❌ Falha ao enviar para {cliente.nome}")
                await db.rollback()
        except Exception as e:
            print(f"❌ Erro no processo de {cliente.nome}: {e}")
            await db.rollback()


async def verificar_e_enviar_lembretes_agendamento(db: AsyncSession):
    """
    Envia lembretes automáticos: 1h antes e 30min antes do agendamento.
    CORREÇÃO: Removeu filtro is_confirmed para pegar todos os agendamentos futuros.
    """
    agora = datetime.now(tz_br)
    hoje = agora.date()
    amanha = hoje + timedelta(days=1)

    # ✅ CORREÇÃO: Busca agendamentos de hoje e amanhã, SEM filtrar por is_confirmed
    # Assim pega tanto os confirmados quanto os pendentes
    stmt = (
        select(Agendamento)
        .options(
            selectinload(Agendamento.cliente),
            selectinload(Agendamento.barbeiro),
            selectinload(Agendamento.servicos),
        )
        .where(
            Agendamento.data.between(hoje, amanha),
            Agendamento.pago == False,
            # Removido: Agendamento.is_confirmed == True
        )
    )
    result = await db.execute(stmt)
    agendamentos = result.scalars().all()

    for agd in agendamentos:
        if not agd.cliente or not agd.cliente.telefone:
            continue

        dt_agendamento = tz_br.localize(datetime.combine(agd.data, agd.hora))
        diferenca = dt_agendamento - agora
        minutos_restantes = diferenca.total_seconds() / 60

        # Pula se já passou ou se é muito distante (> 70min para dar margem à janela de 1h)
        if minutos_restantes < 0 or minutos_restantes > 70:
            continue

        mensagem = ""
        tipo_lembrete = ""
        chave_unico = (
            f"{agd.id}_{minutos_restantes:.0f}"  # Chave única para evitar spam no mesmo minuto
        )

        # Evita enviar se já enviou nos últimos segundos (proteção contra loop rápido)
        if chave_unico in enviados_recentemente:
            continue

        # 🔹 JANELA DE 1 HORA (entre 50min e 70min) - Alarguei um pouco para garantir
        if 50 <= minutos_restantes <= 70:
            lista_servicos = ", ".join([s.nome for s in agd.servicos])
            mensagem = (
                f"⏰ *LEMBRETE: Seu horário é em ~1 hora!*\n\n"
                f"Olá, *{agd.cliente.nome.split()[0]}*! 👋\n\n"
                f"✂️ *Serviços:* {lista_servicos}\n"
                f"📅 *Data:* {agd.data.strftime('%d/%m')}\n"
                f"⏰ *Horário:* {agd.hora.strftime('%H:%M')}\n"
                f"💇‍♂️ *Barbeiro:* {agd.barbeiro.nome if agd.barbeiro else 'Equipe'}\n\n"
                f"Te esperamos! 💈✨"
            )
            tipo_lembrete = "1h"

        # 🔹 JANELA DE 30 MINUTOS (entre 20min e 40min)
        elif 20 <= minutos_restantes <= 40:
            mensagem = (
                f"🚨 *FALTA POUCO!*\n\n"
                f"Olá, *{agd.cliente.nome.split()[0]}*!\n\n"
                f"Seu horário na Barbearia é daqui a *~30 minutos*:\n"
                f"⏰ {agd.hora.strftime('%H:%M')}\n"
                f"📍 {agd.barbeiro.nome if agd.barbeiro else 'Equipe'}\n\n"
                f"Já estamos te esperando! 💈✂️"
            )
            tipo_lembrete = "30min"

        # 🔹 ENVIA MENSAGEM SE DENTRO DA JANELA
        if mensagem:
            try:
                sucesso = await enviar_mensagem_automatica(agd.cliente.telefone, mensagem)

                if sucesso:
                    print(
                        f"✅ Lembrete ({tipo_lembrete}) enviado para {agd.cliente.nome} ({minutos_restantes:.0f}min restantes)"
                    )
                    # Adiciona ao cache para não repetir imediatamente
                    enviados_recentemente.add(chave_unico)
                    # Limpa o cache após alguns minutos para liberar memória (opcional em prod usar Redis TTL)
                    if len(enviados_recentemente) > 100:
                        enviados_recentemente.clear()
                else:
                    print(f"❌ Falha ao enviar lembrete para {agd.cliente.nome}")
            except Exception as e:
                print(f"❌ Erro ao enviar lembrete: {e}")


async def loop_de_verificacao(db_session_maker):
    """Loop infinito que roda a cada 1 minuto."""
    print("🤖 Robô de Lembretes e Aniversários Iniciado...")
    while True:
        try:
            async with db_session_maker() as db:
                await verificar_e_enviar_aniversariantes(db)
                await verificar_e_enviar_lembretes_agendamento(db)
        except Exception as e:
            print(f"❌ Erro no loop de fundo: {e}")

        # Espera 60 segundos
        await asyncio.sleep(60)
