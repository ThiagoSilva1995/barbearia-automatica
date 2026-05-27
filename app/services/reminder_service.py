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

# Configurações de horário para aniversários
HORA_INICIO_ANIVERSARIO = time(8, 0)  # Começa às 08:00
HORA_FIM_ANIVERSARIO = time(23, 0)  # Termina às 23:00
HORA_RESET_DIARIO = time(8, 0)  # Reset do flag às 08:00


async def _reset_aniversariantes_diario(db: AsyncSession, hoje: date):
    """
    Reseta o flag parabens_enviado APENAS para aniversariantes de hoje,
    uma vez por dia, às 08:00 da manhã.
    """
    # Verifica se já executou o reset hoje (usa um cache simples em memória ou tabela auxiliar)
    # Aqui usamos uma abordagem simples: verifica se há aniversariantes com parabens_enviado=True hoje
    stmt_check = select(Cliente).where(
        Cliente.data_nascimento != None,
        Cliente.parabens_enviado == True,
        # Filtra apenas quem faz aniversário hoje
    )
    result = await db.execute(stmt_check)
    clientes_com_flag = result.scalars().all()

    aniversariantes_hoje_com_flag = [
        c
        for c in clientes_com_flag
        if c.data_nascimento.day == hoje.day and c.data_nascimento.month == hoje.month
    ]

    # Se encontrou aniversariantes com flag=True, reseta APENAS eles
    if aniversariantes_hoje_com_flag:
        for c in aniversariantes_hoje_com_flag:
            c.parabens_enviado = False
        await db.commit()
        print(
            f"🔄 Reset diário: {len(aniversariantes_hoje_com_flag)} flags de aniversário resetadas."
        )


async def verificar_e_enviar_aniversariantes(db: AsyncSession):
    """
    Verifica aniversariantes e envia APENAS UMA VEZ no dia, entre 08:00 e 23:00.
    """
    agora = datetime.now(tz_br)
    hoje = agora.date()
    hora_atual = agora.time()

    # ✅ Verifica janela de envio: 08:00 às 23:00
    if hora_atual < HORA_INICIO_ANIVERSARIO or hora_atual >= HORA_FIM_ANIVERSARIO:
        return

    # ✅ Reset diário do flag às 08:00 (executa apenas uma vez por dia)
    if hora_atual.hour == HORA_RESET_DIARIO.hour and hora_atual.minute < 5:
        await _reset_aniversariantes_diario(db, hoje)
        return  # Sai após reset para não enviar na mesma execução

    # Busca clientes que fazem aniversário hoje E ainda não receberam o parabéns
    stmt = select(Cliente).where(
        Cliente.data_nascimento != None, Cliente.parabens_enviado == False
    )
    result = await db.execute(stmt)
    clientes = result.scalars().all()

    # Filtra apenas aniversariantes de hoje
    aniversariantes_do_dia = [
        c
        for c in clientes
        if c.data_nascimento.day == hoje.day and c.data_nascimento.month == hoje.month
    ]

    if not aniversariantes_do_dia:
        return

    print(
        f"🎂 Encontrados {len(aniversariantes_do_dia)} aniversariantes para enviar hoje."
    )

    for cliente in aniversariantes_do_dia:
        try:
            # Verifica se o telefone está válido
            if (
                not cliente.telefone
                or len(str(cliente.telefone).replace(" ", "").replace("-", "")) < 10
            ):
                print(f"⚠️ Telefone inválido para {cliente.nome}, pulando...")
                continue

            msg = gerar_mensagem_aniversario(cliente)
            sucesso = await enviar_mensagem_automatica(cliente.telefone, msg)

            if sucesso:
                print(f"✅ Parabéns enviado para {cliente.nome}")
                # ✅ Marca como enviado e COMMITA imediatamente
                cliente.parabens_enviado = True
                await db.commit()  # Commit EXPLÍCITO para garantir persistência
            else:
                print(f"❌ Falha ao enviar para {cliente.nome}")
                await db.rollback()  # Rollback se falhar
        except Exception as e:
            print(f"❌ Erro no processo de {cliente.nome}: {e}")
            await db.rollback()


async def verificar_e_enviar_lembretes_agendamento(db: AsyncSession):
    """
    Envia lembretes automáticos: 1h antes e 30min antes do agendamento.
    Usa janelas de tempo para evitar repetição.
    """
    agora = datetime.now(tz_br)
    hoje = agora.date()
    amanha = hoje + timedelta(days=1)

    # Busca agendamentos de hoje e amanhã (apenas confirmados/não pagos)
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
            Agendamento.is_confirmed == True,
        )
    )
    result = await db.execute(stmt)
    agendamentos = result.scalars().all()

    for agd in agendamentos:
        if not agd.cliente or not agd.cliente.telefone:
            continue

        # Combina data e hora do agendamento no timezone correto
        dt_agendamento = tz_br.localize(datetime.combine(agd.data, agd.hora))
        diferenca = dt_agendamento - agora
        minutos_restantes = diferenca.total_seconds() / 60

        # Pula se já passou ou se é muito distante
        if minutos_restantes < 0 or minutos_restantes > 120:
            continue

        mensagem = ""
        enviar = False

        # 🔹 JANELA DE 1 HORA (entre 55min e 65min)
        if 55 <= minutos_restantes <= 65:
            lista_servicos = ", ".join([s.nome for s in agd.servicos])
            mensagem = (
                f"⏰ *LEMBRETE: Seu horário é em 1 hora!*\n\n"
                f"Olá, *{agd.cliente.nome.split()[0]}*! 👋\n\n"
                f"✂️ *Serviços:* {lista_servicos}\n"
                f"📅 *Data:* {agd.data.strftime('%d/%m')}\n"
                f"⏰ *Horário:* {agd.hora.strftime('%H:%M')}\n"
                f"💇‍♂️ *Barbeiro:* {agd.barbeiro.nome if agd.barbeiro else 'Equipe'}\n\n"
                f"Chegue com 5 minutos de antecedência. Qualquer imprevisto, nos avise!\n"
                f"Te esperamos! 💈✨"
            )
            enviar = True

        # 🔹 JANELA DE 30 MINUTOS (entre 25min e 35min)
        elif 25 <= minutos_restantes <= 35:
            mensagem = (
                f"🚨 *FALTA POUCO!*\n\n"
                f"Olá, *{agd.cliente.nome.split()[0]}*!\n\n"
                f"Seu horário na Barbearia é daqui a *30 minutos*:\n"
                f"⏰ {agd.hora.strftime('%H:%M')}\n"
                f"📍 {agd.barbeiro.nome if agd.barbeiro else 'Equipe'}\n\n"
                f"Já estamos te esperando! 💈✂️"
            )
            enviar = True

        # 🔹 ENVIA MENSAGEM SE DENTRO DA JANELA
        if enviar and mensagem:
            try:
                sucesso = await enviar_mensagem_automatica(
                    agd.cliente.telefone, mensagem
                )

                if sucesso:
                    print(
                        f"✅ Lembrete enviado para {agd.cliente.nome} ({minutos_restantes:.0f}min restantes)"
                    )
                else:
                    print(f"❌ Falha ao enviar lembrete para {agd.cliente.nome}")
            except Exception as e:
                print(f"❌ Erro ao enviar lembrete: {e}")


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
