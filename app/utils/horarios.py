# app/utils/horarios.py
from datetime import datetime, time, date, timedelta
import pytz
from sqlalchemy import select
from typing import List, Tuple

from app.models.bloqueio import BloqueioHorario
from app.models import Agendamento

tz_br = pytz.timezone("America/Sao_Paulo")

# =============================================================================
# CONFIGURAÇÕES PADRÃO
# =============================================================================
DEFAULT_HORARIOS = {
    "inicio_m": time(8, 30),
    "fim_m": time(12, 0),
    "inicio_t": time(14, 0),
    "fim_t": time(18, 30),
}

# =============================================================================
# FUNÇÕES AUXILIARES INTERNAS
# =============================================================================


def _parse_horario_config(valor: str, padrao: time) -> time:
    """Converte string de horário para objeto time, usando padrão se falhar."""
    if not valor:
        return padrao
    try:
        return datetime.strptime(valor, "%H:%M").time()
    except Exception:
        return padrao


def _gerar_periodo_slots(data_alvo: date, inicio: time, fim: time, passo_minutos: int) -> List[str]:
    """Gera lista de strings de horário (HH:MM) entre início e fim."""
    slots = []
    if inicio >= fim:
        return slots

    atual = datetime.combine(data_alvo, inicio)
    fim_dt = datetime.combine(data_alvo, fim)

    while atual <= fim_dt:
        slots.append(atual.strftime("%H:%M"))
        atual += timedelta(minutes=passo_minutos)

    return slots


def _calcular_minutos(hora: time) -> int:
    """Converte objeto time para minutos totais do dia."""
    return hora.hour * 60 + hora.minute


def _verificar_sobreposição(
    min_inicio_novo: int, min_fim_novo: int, min_inicio_occ: int, min_fim_occ: int
) -> bool:
    """Verifica se dois intervalos de tempo se sobrepõem."""
    return min_inicio_novo < min_fim_occ and min_fim_novo > min_inicio_occ


# =============================================================================
# FUNÇÕES PÚBLICAS DE GERAÇÃO DE SLOTS
# =============================================================================
# app/utils/horarios.py


async def gerar_slots_disponiveis(
    db, config, data_alvo: date, passo_minutos: int = 10
) -> List[str]:
    """
    Gera slots disponíveis considerando configurações gerais e bloqueios específicos.
    """
    hoje = datetime.now(tz_br).date()
    agora = datetime.now(tz_br)
    dia_semana = data_alvo.weekday()

    # 1. Obter horários base da configuração
    base_inicio_m = _parse_horario_config(config.horario_inicio_manha, DEFAULT_HORARIOS["inicio_m"])
    base_fim_m = _parse_horario_config(config.horario_fim_manha, DEFAULT_HORARIOS["fim_m"])
    base_inicio_t = _parse_horario_config(config.horario_inicio_tarde, DEFAULT_HORARIOS["inicio_t"])
    base_fim_t = _parse_horario_config(config.horario_fim_tarde, DEFAULT_HORARIOS["fim_t"])

    # 2. Verificar bloqueios específicos do dia
    stmt = select(BloqueioHorario).where(BloqueioHorario.data == data_alvo)
    res = await db.execute(stmt)
    bloqueio = res.scalars().first()

    # Variáveis para armazenar os horários efetivos do dia
    inicio_m, fim_m = None, None
    inicio_t, fim_t = None, None

    if bloqueio:
        print(f"🔍 Bloqueio encontrado para {data_alvo}: Tipo={bloqueio.tipo}")

        if bloqueio.tipo == "FECHADO":
            return []

        elif bloqueio.tipo == "SO_MANHA":
            inicio_m, fim_m = base_inicio_m, base_fim_m

        elif bloqueio.tipo == "SO_TARDE":
            inicio_t, fim_t = base_inicio_t, base_fim_t

        elif bloqueio.tipo == "PERSONALIZADO":
            # ✅ CORREÇÃO: Acessa os atributos corretamente e converte para time se necessário
            # Assumindo que o modelo salva como string 'HH:MM' ou objeto time

            # Tenta pegar Manhã
            h_inicio_m = getattr(bloqueio, "horario_inicio_manha", None)
            h_fim_m = getattr(bloqueio, "horario_fim_manha", None)

            if h_inicio_m and h_fim_m:
                # Se já for objeto time, usa direto. Se for string, converte.
                if isinstance(h_inicio_m, str):
                    try:
                        inicio_m = datetime.strptime(h_inicio_m, "%H:%M").time()
                        fim_m = datetime.strptime(h_fim_m, "%H:%M").time()
                    except Exception as e:
                        print(f"⚠️ Erro ao converter horário manhã personalizado: {e}")
                else:
                    inicio_m = h_inicio_m
                    fim_m = h_fim_m

            # Tenta pegar Tarde
            h_inicio_t = getattr(bloqueio, "horario_inicio_tarde", None)
            h_fim_t = getattr(bloqueio, "horario_fim_tarde", None)

            if h_inicio_t and h_fim_t:
                if isinstance(h_inicio_t, str):
                    try:
                        inicio_t = datetime.strptime(h_inicio_t, "%H:%M").time()
                        fim_t = datetime.strptime(h_fim_t, "%H:%M").time()
                    except Exception as e:
                        print(f"⚠️ Erro ao converter horário tarde personalizado: {e}")
                else:
                    inicio_t = h_inicio_t
                    fim_t = h_fim_t

            print(
                f"🕒 Horários Personalizados Definidos: M={inicio_m}-{fim_m} | T={inicio_t}-{fim_t}"
            )

        else:
            inicio_m, fim_m = base_inicio_m, base_fim_m
            inicio_t, fim_t = base_inicio_t, base_fim_t
    else:
        # Lógica padrão sem bloqueio
        if dia_semana == 6:  # Domingo
            return []

        inicio_m, fim_m = base_inicio_m, base_fim_m
        inicio_t, fim_t = base_inicio_t, base_fim_t

        # Regra Sábado: Fecha meio-dia (padrão)
        if dia_semana == 5:
            limite_sabado = time(12, 0)
            if fim_m > limite_sabado:
                fim_m = limite_sabado
            inicio_t, fim_t = None, None  # Invalida tarde no sábado padrão

    # 3. Gerar slots brutos
    slots_gerados = []

    # Gera manhã SE houver horários válidos definidos
    if inicio_m and fim_m and inicio_m < fim_m:
        slots_gerados.extend(_gerar_periodo_slots(data_alvo, inicio_m, fim_m, passo_minutos))
        print(f"✅ Slots Manhã gerados: {len(slots_gerados)}")

    # Gera tarde SE houver horários válidos definidos
    if inicio_t and fim_t and inicio_t < fim_t:
        slots_gerados.extend(_gerar_periodo_slots(data_alvo, inicio_t, fim_t, passo_minutos))
        print(f"✅ Slots Tarde gerados. Total agora: {len(slots_gerados)}")

    # 4. Filtrar slots passados se for hoje
    if data_alvo == hoje:
        hora_atual_str = agora.strftime("%H:%M")
        slots_gerados = [s for s in slots_gerados if s > hora_atual_str]

    return slots_gerados


def filtrar_conflitos(
    slots_gerados: List[str],
    agendamentos_ocupados: List[Tuple[time, int]],
    duracao_necessaria: int,
    buffer: int = 10,
) -> List[str]:
    """
    Filtra slots que colidem com agendamentos existentes.
    """
    horarios_livres = []
    tempo_total = duracao_necessaria + buffer

    for h_str in slots_gerados:
        h_time = datetime.strptime(h_str, "%H:%M").time()
        min_inicio_novo = _calcular_minutos(h_time)
        min_fim_novo = min_inicio_novo + tempo_total

        esta_livre = True

        for occ_hora, occ_duracao in agendamentos_ocupados:
            dur_real = occ_duracao if occ_duracao else 30
            min_inicio_occ = _calcular_minutos(occ_hora)
            min_fim_occ = min_inicio_occ + dur_real + buffer

            if _verificar_sobreposição(min_inicio_novo, min_fim_novo, min_inicio_occ, min_fim_occ):
                esta_livre = False
                break

        if esta_livre:
            horarios_livres.append(h_str)

    return horarios_livres


async def gerar_slots_admin(db, data_alvo: date, passo_minutos: int = 60) -> List[str]:
    """
    Gera horários para ADMIN sem restrição de horário de funcionamento.
    Gera slots das 00:00 às 23:00, removendo apenas os que colidem com agendamentos existentes.
    """
    # 1. Gerar todos os slots possíveis do dia (de 00:00 a 23:00)
    slots_gerados = []
    inicio_dia = datetime.combine(data_alvo, time(0, 0))

    for i in range(24):
        hora_atual = inicio_dia + timedelta(hours=i)
        slots_gerados.append(hora_atual.strftime("%H:%M"))

    # 2. Buscar agendamentos ocupados do dia
    stmt_ocupados = select(Agendamento.hora, Agendamento.duracao_minutos).where(
        Agendamento.data == data_alvo
    )
    ocupados_res = await db.execute(stmt_ocupados)
    ocupados = ocupados_res.all()

    # 3. Filtrar conflitos (Buffer 0 para máxima liberdade do admin)
    horarios_livres = filtrar_conflitos(
        slots_gerados,
        ocupados,
        duracao_necessaria=30,
        buffer=0,
    )

    return horarios_livres
