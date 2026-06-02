# app/utils/horarios.py
from datetime import datetime, time, date, timedelta
import pytz
from sqlalchemy import select
from app.models.bloqueio import BloqueioHorario
from app.models import Agendamento

tz_br = pytz.timezone("America/Sao_Paulo")


async def gerar_slots_disponiveis(db, config, data_alvo: date, passo_minutos: int = 10):
    """
    Gera slots considerando configurações gerais E bloqueios específicos do dia.
    Se for SO_MANHA, usa apenas o turno da manhã definido na Configuração Geral.
    """
    hoje = datetime.now(tz_br).date()
    agora = datetime.now(tz_br)
    dia_semana = data_alvo.weekday()

    # 1. Verificar se há bloqueio para esta data
    stmt = select(BloqueioHorario).where(BloqueioHorario.data == data_alvo)
    res = await db.execute(stmt)
    bloqueio = res.scalars().first()

    slots = []

    # Definição dos horários base (da Configuração Geral)
    try:
        base_inicio_m = datetime.strptime(config.horario_inicio_manha or "08:30", "%H:%M").time()
        base_fim_m = datetime.strptime(
            config.horario_fim_manha or "12:00", "%H:%M"
        ).time()  # Ajustei padrão para 12:00
        base_inicio_t = datetime.strptime(config.horario_inicio_tarde or "14:00", "%H:%M").time()
        base_fim_t = datetime.strptime(config.horario_fim_tarde or "18:30", "%H:%M").time()
    except Exception:
        base_inicio_m, base_fim_m = time(8, 30), time(12, 0)
        base_inicio_t, base_fim_t = time(14, 0), time(18, 30)

    # Lógica de Sobreposição de Bloqueio
    if bloqueio:
        if bloqueio.tipo == "FECHADO":
            return []  # Não gera nada

        elif bloqueio.tipo == "SO_MANHA":
            # Usa APENAS a manhã configurada. Tarde fica inválida.
            inicio_m, fim_m = base_inicio_m, base_fim_m
            inicio_t, fim_t = time(23, 59), time(23, 59)  # Horário inválido para não gerar tarde

        elif bloqueio.tipo == "SO_TARDE":
            # Usa APENAS a tarde configurada. Manhã fica inválida.
            inicio_m, fim_m = time(0, 0), time(0, 1)  # Horário inválido para não gerar manhã
            inicio_t, fim_t = base_inicio_t, base_fim_t

        elif bloqueio.tipo == "PERSONALIZADO":
            # Usa os horários específicos do bloqueio se existirem, senão usa o padrão
            inicio_m = bloqueio.horario_inicio_manha or base_inicio_m
            fim_m = bloqueio.horario_fim_manha or base_fim_m
            inicio_t = bloqueio.horario_inicio_tarde or base_inicio_t
            fim_t = bloqueio.horario_fim_tarde or base_fim_t
        else:
            # Fallback
            inicio_m, fim_m = base_inicio_m, base_fim_m
            inicio_t, fim_t = base_inicio_t, base_fim_t
    else:
        # Sem bloqueio, usa configuração normal + regra de sábado/domingo
        if dia_semana == 6:  # Domingo
            return []

        inicio_m, fim_m = base_inicio_m, base_fim_m
        inicio_t, fim_t = base_inicio_t, base_fim_t

        # Regra Sábado: Fecha 12:00 (se não houver bloqueio personalizado sobrescrevendo)
        if dia_semana == 5:
            limite_sabado = time(12, 0)
            if fim_m > limite_sabado:
                fim_m = limite_sabado
            inicio_t, fim_t = time(23, 59), time(23, 59)  # Invalida tarde no sábado

    def _gerar_periodo(inicio, fim):
        if inicio >= fim:
            return  # Segurança
        atual = datetime.combine(data_alvo, inicio)
        fim_dt = datetime.combine(data_alvo, fim)

        while atual <= fim_dt:
            slots.append(atual.strftime("%H:%M"))
            atual += timedelta(minutes=passo_minutos)

    _gerar_periodo(inicio_m, fim_m)
    if inicio_t < fim_t:
        _gerar_periodo(inicio_t, fim_t)

    # Filtro Hoje: Remove slots passados
    if data_alvo == hoje:
        hora_atual_str = agora.strftime("%H:%M")
        slots = [s for s in slots if s > hora_atual_str]

    return slots


def filtrar_conflitos(slots_gerados, agendamentos_ocupados, duracao_necessaria, buffer=10):
    """
    Recebe todos os slots possíveis e remove aqueles que colidem com agendamentos existentes.
    """
    horarios_livres = []
    tempo_total = duracao_necessaria + buffer

    for h_str in slots_gerados:
        h_time = datetime.strptime(h_str, "%H:%M").time()

        min_inicio_novo = h_time.hour * 60 + h_time.minute
        min_fim_novo = min_inicio_novo + tempo_total

        esta_livre = True

        for occ_hora, occ_duracao in agendamentos_ocupados:
            dur_real = occ_duracao if occ_duracao else 30

            min_inicio_occ = occ_hora.hour * 60 + occ_hora.minute
            min_fim_occ = min_inicio_occ + dur_real + buffer

            if min_inicio_novo < min_fim_occ and min_fim_novo > min_inicio_occ:
                esta_livre = False
                break

        if esta_livre:
            horarios_livres.append(h_str)

    return horarios_livres


async def gerar_slots_admin(db, data_alvo: date, passo_minutos: int = 60):
    """
    Gera horários para ADMIN sem restrição de horário de funcionamento.
    Gera slots das 00:00 às 23:59, removendo apenas os que colidem com agendamentos existentes.
    """
    # 1. Gerar todos os slots possíveis do dia (de 00:00 a 23:00)
    slots_gerados = []
    inicio_dia = datetime.combine(data_alvo, time(0, 0))

    # Vamos gerar de hora em hora para não ficar pesado, mas pode mudar para 30 se quiser
    for i in range(24):
        hora_atual = inicio_dia + timedelta(hours=i)
        slots_gerados.append(hora_atual.strftime("%H:%M"))

        # Se quiser slots de 30 em 30 min, descomente abaixo:
        # meia_hora = hora_atual + timedelta(minutes=30)
        # slots_gerados.append(meia_hora.strftime("%H:%M"))

    # 2. Buscar agendamentos ocupados do dia
    stmt_ocupados = select(Agendamento.hora, Agendamento.duracao_minutos).where(
        Agendamento.data == data_alvo
    )
    ocupados_res = await db.execute(stmt_ocupados)
    ocupados = ocupados_res.all()

    # 3. Filtrar conflitos (usando a função existente, mas com buffer 0 ou pequeno para admin)
    # Para admin, vamos usar buffer 0 para permitir agendar "colado" se ele quiser,
    # ou pode manter 10 se preferir segurança.
    horarios_livres = filtrar_conflitos(
        slots_gerados,
        ocupados,
        duracao_necessaria=30,  # Assume serviço padrão de 30min para verificação inicial
        buffer=0,  # Buffer 0 para máxima liberdade
    )

    return horarios_livres
