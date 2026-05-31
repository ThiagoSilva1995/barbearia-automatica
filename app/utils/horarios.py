from datetime import datetime, time, date, timedelta
import pytz

tz_br = pytz.timezone("America/Sao_Paulo")


def gerar_slots_disponiveis(config, data_alvo: date, passo_minutos: int = 10):
    """
    Gera TODOS os slots possíveis em intervalos fixos (ex: a cada 10 min).
    Isso permite que o filtro de conflito encontre 'buracos' na agenda.
    Ex: 08:30, 08:40, 08:50... em vez de pular direto para 09:20.
    """
    hoje = datetime.now(tz_br).date()
    agora = datetime.now(tz_br)
    dia_semana = data_alvo.weekday()

    if dia_semana == 6:  # Domingo fechado
        return []

    slots = []

    try:
        inicio_m = datetime.strptime(config.horario_inicio_manha or "08:30", "%H:%M").time()
        fim_m = datetime.strptime(config.horario_fim_manha or "11:00", "%H:%M").time()
        inicio_t = datetime.strptime(config.horario_inicio_tarde or "14:00", "%H:%M").time()
        fim_t = datetime.strptime(config.horario_fim_tarde or "18:30", "%H:%M").time()
    except Exception:
        inicio_m, fim_m = time(8, 30), time(11, 0)
        inicio_t, fim_t = time(14, 0), time(18, 30)

    # Regra Sábado: Fecha 12:00
    if dia_semana == 5:
        limite_sabado = time(12, 0)
        if fim_m > limite_sabado:
            fim_m = limite_sabado
        inicio_t, fim_t = time(23, 0), time(22, 0)  # Invalida tarde

    def _gerar_periodo(inicio, fim):
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

        # Convertendo tudo para minutos do dia para facilitar a conta matemática
        min_inicio_novo = h_time.hour * 60 + h_time.minute
        min_fim_novo = min_inicio_novo + tempo_total

        esta_livre = True

        for occ_hora, occ_duracao in agendamentos_ocupados:
            # Garante que occ_duracao não seja None (fallback para 30min)
            dur_real = occ_duracao if occ_duracao else 30

            min_inicio_occ = occ_hora.hour * 60 + occ_hora.minute
            min_fim_occ = min_inicio_occ + dur_real + buffer

            # Verifica sobreposição: (InícioA < FimB) e (FimA > InícioB)
            if min_inicio_novo < min_fim_occ and min_fim_novo > min_inicio_occ:
                esta_livre = False
                break

        if esta_livre:
            horarios_livres.append(h_str)

    return horarios_livres
