import urllib.parse
import httpx
from app.models.cliente import Cliente

# ==========================================================
# CONFIGURAÇÕES DA EVOLUTION API (LOCAL)
# ==========================================================


import os
API_KEY = os.getenv("EVOLUTION_API_KEY", "sua_chave_secreta_123")
EVOLUTION_API_URL = "http://evolution_api:8080"
INSTANCE_NAME = "Barbearia_Online"


async def enviar_mensagem_automatica(telefone: str, mensagem: str) -> bool:
    """Envia mensagem via Evolution API v1.8.0."""
    # Limpa e formata o telefone
    tel_limpo = "".join(filter(str.isdigit, telefone))
    if not tel_limpo.startswith("55"):
        tel_limpo = "55" + tel_limpo.lstrip("0")

    # Payload no formato CORRETO para Evolution API v1.8.0
    payload = {
    "number": tel_limpo,
    "textMessage": {"text": mensagem},  # ✅ CORRETO!
    "presence": "composing",
}

    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/json"
    }

    try:
        # Aumenta timeout para 30 segundos (API pode ser lenta)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}",
                json=payload,
                headers=headers,
            )
            
            # Log detalhado para debug
            print(f"📤 Enviando para {tel_limpo}: Status {response.status_code}")
            print(f"📦 Resposta: {response.text[:200]}")
            
            if response.status_code in [200, 201, 202]:
                print(f"✅ [AUTO] Mensagem enviada para {telefone}")
                return True
            else:
                print(f"❌ [ERRO API] {response.status_code}: {response.text}")
                return False
                
    except httpx.ConnectError as e:
        print(f"❌ [ERRO CONEXÃO] Não foi possível conectar à Evolution API: {e}")
        return False
    except httpx.TimeoutException as e:
        print(f"❌ [ERRO TIMEOUT] A API demorou demais para responder: {e}")
        return False
    except Exception as e:
        print(f"❌ [ERRO DESCONHECIDO] {type(e).__name__}: {e}")
        return False

def gerar_link_whatsapp(telefone: str, mensagem: str) -> str:
    """Gera link manual."""
    tel_limpo = "".join(filter(str.isdigit, telefone))
    if not tel_limpo.startswith("55"):
        tel_limpo = "55" + tel_limpo.lstrip("0")
    msg_codificada = urllib.parse.quote(mensagem)
    return f"https://wa.me/{tel_limpo}?text={msg_codificada}"


def gerar_mensagem_aniversario(
    cliente: Cliente, texto_personalizado: str = None
) -> str:
    """Gera mensagem de aniversário."""
    primeiro_nome = cliente.nome.split()[0]
    if texto_personalizado:
        return texto_personalizado.replace("{nome}", primeiro_nome)
    return (
        f"🎉 Feliz Aniversário, *{primeiro_nome}*! 🎉\n\n"
        f"A *Barbearia do Thales* te deseja um dia incrível!\n\n"
        f"Um grande abraço!\n💈"
    )


# --- FUNÇÃO QUE ESTAVA FALTANDO ---
async def enviar_parabens_aniversariantes(
    db, aniversariantes, texto_personalizado=None
):
    """Envia parabéns para a lista de aniversariantes."""
    resultados = []
    for cliente in aniversariantes:
        msg = gerar_mensagem_aniversario(cliente, texto_personalizado)

        # Tenta envio automático
        sucesso = await enviar_mensagem_automatica(cliente.telefone, msg)

        if sucesso:
            resultados.append(
                {"cliente": cliente, "status": "enviado_auto", "mensagem": msg}
            )
        else:
            # Fallback: gera link manual se falhar
            link = gerar_link_whatsapp(cliente.telefone, msg)
            resultados.append(
                {
                    "cliente": cliente,
                    "status": "falha_manual",
                    "link": link,
                    "mensagem": msg,
                }
            )

    return resultados


def gerar_mensagem_novo_agendamento(
    cliente_nome, servicos_nomes, data_str, hora_str, barbeiro_nome
):
    """Gera mensagem de novo agendamento."""
    lista_servicos = ", ".join(servicos_nomes)
    return (
        f"💈 *NOVO AGENDAMENTO REALIZADO!* 💈\n\n"
        f"👤 *Cliente:* {cliente_nome}\n"
        f"✂️ *Serviços:* {lista_servicos}\n"
        f"📅 *Data:* {data_str}\n"
        f"⏰ *Horário:* {hora_str}\n"
        f"💇‍️ *Barbeiro:* {barbeiro_nome}\n\n"
        f"_Aguardando confirmação._"
    )


def gerar_mensagem_alteracao_agendamento(
    cliente_nome, data_antiga, hora_antiga, data_nova, hora_nova, servicos_nomes
):
    """Gera mensagem de alteração de agendamento."""
    lista_servicos = ", ".join(servicos_nomes)
    return (
        f"⚠️ *ALTERAÇÃO DE AGENDAMENTO!* ⚠️\n\n"
        f"👤 *Cliente:* {cliente_nome}\n"
        f"✂️ *Serviços:* {lista_servicos}\n\n"
        f"❌ *ANTIGO:* {data_antiga} às {hora_antiga}\n"
        f"✅ *NOVO:* {data_nova} às {hora_nova}\n\n"
        f"_Por favor, confirme._"
    )


def gerar_mensagem_cancelamento(
    cliente_nome, data_str, hora_str, barbeiro_nome, servicos_nomes
):
    """Gera mensagem de cancelamento."""
    lista_servicos = ", ".join(servicos_nomes)
    return (
        f"❌ *CANCELAMENTO DE AGENDAMENTO* ❌\n\n"
        f"👤 *Cliente:* {cliente_nome}\n"
        f"✂️ *Serviços:* {lista_servicos}\n"
        f"📅 *Data:* {data_str}\n"
        f"⏰ *Horário:* {hora_str}\n"
        f"💇‍♂️ *Barbeiro:* {barbeiro_nome}\n\n"
        f"_O horário foi liberado._"
    )


def gerar_mensagem_confirmacao_cliente(
    cliente_nome, data_str, hora_str, barbeiro_nome, servicos_nomes
):
    """Gera a mensagem de confirmação enviada PARA O CLIENTE."""
    lista_servicos = ", ".join(servicos_nomes)

    mensagem = (
        f"✅ *AGENDAMENTO CONFIRMADO!* ✅\n\n"
        f"Olá, *{cliente_nome}*! Seu horário na Barbearia está garantido.\n\n"
        f"✂️ *Serviços:* {lista_servicos}\n"
        f"📅 *Data:* {data_str}\n"
        f"⏰ *Horário:* {hora_str}\n"
        f"💇‍♂️ *Barbeiro:* {barbeiro_nome}\n\n"
        f"Chegue com 5 minutos de antecedência. Qualquer imprevisto, nos avise!\n"
        f"Te esperamos! 💈✨"
    )
    return mensagem
