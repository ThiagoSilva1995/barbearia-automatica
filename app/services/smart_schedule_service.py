from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import date, time
import pytz
from app.models import Agendamento, Cliente
from app.services.whatsapp_service import enviar_mensagem_automatica

tz_br = pytz.timezone("America/Sao_Paulo")


def gerar_mensagem_oportunidade(
    cliente_nome: str, horario_oferta: str, horario_atual: str, data_str: str
):
    """Gera a mensagem persuasiva para o cliente mudar de horário."""
    return (
        f"⚡ *OPORTUNIDADE RELÂMPAGO!* ⚡\n\n"
        f"Olá, *{cliente_nome}*! Tudo bem?\n\n"
        f"Liberou um horário às *{horario_oferta}* hoje ({data_str}), logo antes do seu agendamento atual ({horario_atual}).\n\n"
        f"Quer aproveitar para vir mais cedo e sair mais cedo? 😎\n"
        f"Basta clicar no link abaixo e remarcar para esse horário:\n"
        f"👉 https://seusistema.com/cliente/agendar\n\n"
        f"Te esperamos! 💈✨"
    )


async def disparar_efeito_dominio(
    db, horario_libero_data: date, horario_libero_hora: time
):
    """
    Quando um horário X libera, avisa o cliente do horário Y (o próximo imediato)
    que ele pode mudar para X.
    """

    # 1. Encontrar o PRÓXIMO agendamento confirmado após o horário que liberou
    # Busca no mesmo dia, hora maior que a liberada, ordenado do mais cedo para o mais tarde
    stmt = (
        select(Agendamento)
        .options(selectinload(Agendamento.cliente))
        .where(
            Agendamento.data == horario_libero_data,
            Agendamento.hora > horario_libero_hora,
            # Opcional: Filtrar apenas não pagos se quiser focar neles, ou remover para todos
            # Agendamento.pago == False
        )
        .order_by(Agendamento.hora.asc())
        .limit(1)  # Pega APENAS o imediatamente seguinte
    )

    result = await db.execute(stmt)
    proximo_agd = result.scalars().first()

    if not proximo_agd or not proximo_agd.cliente:
        # Não há ninguém depois para avisar, fim da cadeia por enquanto.
        return

    cliente = proximo_agd.cliente
    horario_atual_cliente = proximo_agd.hora.strftime("%H:%M")
    horario_oferta = horario_libero_hora.strftime("%H:%M")
    data_fmt = horario_libero_data.strftime("%d/%m")

    # 2. Gerar e Enviar Mensagem
    msg = gerar_mensagem_oportunidade(
        cliente_nome=cliente.nome.split()[0],
        horario_oferta=horario_oferta,
        horario_atual=horario_atual_cliente,
        data_str=data_fmt,
    )

    print(
        f"🔔 [EFEITO DOMINÓ] Oferecendo {horario_oferta} para {cliente.nome} (atual: {horario_atual_cliente})"
    )

    try:
        sucesso = await enviar_mensagem_automatica(cliente.telefone, msg)
        if sucesso:
            print(f"✅ Oferta enviada com sucesso para {cliente.nome}")
        else:
            print(f"❌ Falha ao enviar oferta para {cliente.nome}")
    except Exception as e:
        print(f"❌ Erro no envio da oferta: {e}")

    # Nota: A próxima etapa da cadeia (avisar o das 16h se o das 15h mudar)
    # ocorrerá AUTOMATICAMENTE quando o cliente das 15h editar o agendamento dele,
    # pois a edição também chamará esta função recursivamente.
