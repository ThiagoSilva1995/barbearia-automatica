# 🔔 Sistema de Notificações em Tempo Real - Guia Completo

## 📋 O que foi implementado

Sistema completo de notificações in-app com as seguintes funcionalidades:

### ✅ Funcionalidades Principais

1. **🔔 Sino de Notificações no Header**
   - Badge vermelho com contador de notificações não lidas
   - Animação pulsante quando chega nova notificação
   - Dropdown com lista das últimas 10 notificações

2. **🔊 Alerta Sonoro**
   - Som de campainha (gerado via Web Audio API)
   - Botão para mutar/desmutar (🔊/🔇)
   - Preferência salva no navegador (localStorage)

3. **⚡ Tempo Real (Polling)**
   - Verifica novas notificações a cada 3 segundos
   - Quase tempo real sem necessidade de WebSocket
   - Baixo consumo de recursos

4. **🚀 Redirecionamento Inteligente**
   - Ao clicar na notificação, redireciona para o agendamento
   - Se for hoje: `/agendamentos?data=HOJE&destaque=ID`
   - Se for outro dia: `/agendamentos?data=DIA&destaque=ID`
   - Agendamento aparece destacado em amarelo com animação

5. **📊 Notificações Automáticas**
   - ✅ Novo agendamento (cliente ou admin)
   - 🔄 Agendamento alterado
   - ❌ Agendamento cancelado
   - 💰 Pagamento confirmado
   - ⏰ Lembrete 1h enviado
   - 🚨 Lembrete 30min enviado
   - 🎂 Aniversário enviado

---

## 🏗️ Arquivos Modificados

### Backend (Python)

| Arquivo | Alteração |
|---------|-----------|
| `app/routers/cliente_publico.py` | ✅ Cria notificação quando cliente agenda/altera/cancela |
| `app/routers/agenda.py` | ✅ Cria notificação quando admin agenda/altera/cancela |
| `app/routers/notificacoes.py` | ✅ Endpoints API para notificações |
| `app/services/notificacao_service.py` | ✅ Serviço completo de notificações |
| `app/models/notificacao.py` | ✅ Modelo com campos para redirecionamento |

### Frontend (HTML/JS/CSS)

| Arquivo | Alteração |
|---------|-----------|
| `app/templates/base.html` | ✅ Adicionado sino + dropdown + estilos |
| `app/static/js/notificacoes.js` | ✅ Polling + som + animações |
| `app/templates/agendamentos/agendamentos.html` | ✅ Destaque visual do agendamento |

---

## 🎯 Como Funciona

### Fluxo Completo

```
1. CLIENTE agenda online
   ↓
2. SISTEMA cria agendamento no banco
   ↓
3. SISTEMA cria notificação in-app
   ↓
4. SISTEMA envia WhatsApp (paralelo)
   ↓
5. NAVEGADOR DO ADMIN (polling a cada 3s)
   ↓
6. DETECTA nova notificação
   ↓
7. 🔔 Sino pulsa + 🔊 Som toca + 🔴 Badge aparece
   ↓
8. ADMIN clica no sino
   ↓
9. 📋 Dropdown mostra notificações
   ↓
10. ADMIN clica na notificação
    ↓
11. 🚀 Redireciona para /agendamentos?data=DIA&destaque=ID
    ↓
12. ✨ Agendamento aparece destacado em amarelo
```

---

## 🧪 Como Testar

### Passo 1: Reiniciar o Container

```bash
docker compose restart app
```

### Passo 2: Acessar o Sistema

1. Abra o navegador em: `http://localhost:8000`
2. Faça login como admin
3. Você verá o sino 🔔 no canto superior direito

### Passo 3: Testar Notificação

**Opção A: Cliente agenda online**
1. Abra outra aba/janela do navegador
2. Acesse: `http://localhost:8000/cliente`
3. Digite o telefone de um cliente cadastrado
4. Faça um agendamento
5. **Volte para a aba do admin**
6. Você verá:
   - 🔔 Sino pulsando
   - 🔴 Badge vermelho com "1"
   - 🔊 Som de campainha tocando

**Opção B: Admin agenda**
1. Clique em "Novo Agendamento"
2. Preencha os dados e confirme
3. **Abra outra aba do navegador**
4. Faça login como outro admin ou recepção
5. Você verá a notificação chegando

### Passo 4: Testar Redirecionamento

1. Clique no sino 🔔
2. Clique na notificação
3. Você será redirecionado para a tela de agendamentos
4. O agendamento específico aparecerá:
   - ✅ Destacado em amarelo
   - ✅ Com borda lateral amarela
   - ✅ Com animação de pulse por 5 segundos
   - ✅ Scroll automático até ele

### Passo 5: Testar Som

1. Clique no botão 🔊 ao lado de "Marcar todas"
2. O som será mutado (aparecerá 🔇)
3. Faça um novo agendamento
4. **O som NÃO tocará**
5. Clique novamente para reativar

---

## 🎨 Visual

### Sino sem notificações
```
[🔔]
```

### Sino com notificações
```
[🔔 🔴]
     ↑
   Badge vermelho com número
```

### Dropdown aberto
```
┌─────────────────────────────────┐
│ 🔔 Notificações    🔊 Marcar todas │
├─────────────────────────────────┤
│ ✅ Novo Agendamento: João Silva   │
│ 👤 Cliente: João Silva            │
│ 📅 Hoje às 14:30                  │
│ 💇 Carlos                         │
│ ✂️ Corte, Barba                   │
├─────────────────────────────────┤
│ 🔄 Agendamento Alterado: Maria    │
│ 📅 Amanhã às 10:00                │
├─────────────────────────────────┤
│ Ver todas as notificações →       │
└─────────────────────────────────┘
```

### Agendamento destacado
```
| Horário | Cliente  | Barbeiro | Serviços | Status |
|─────────|──────────|──────────|──────────|────────|
| 14:30→  | João     | Carlos   | Corte    | Pago   | ← DESTACADO
| 15:00→  | Maria    | Carlos   | Barba    | Pend.  |   (amarelo)
```

---

## ⚙️ Configurações

### Intervalo de Polling

No arquivo `app/static/js/notificacoes.js`:

```javascript
const CONFIG = {
    INTERVALO_POLLING: 3000, // 3 segundos (padrão)
    // Mude para 5000 para 5 segundos, etc.
};
```

### Volume do Som

No arquivo `app/static/js/notificacoes.js`, função `tocarSom()`:

```javascript
gainNode.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.01);
// Mude 0.3 para 0.5 (mais alto) ou 0.1 (mais baixo)
```

### Frequência do Som

```javascript
oscillator.frequency.value = 800; // Frequência em Hz
// Mude para 600 (som mais grave) ou 1000 (som mais agudo)
```

---

## 🔧 Solução de Problemas

### Problema: Sino não aparece

**Causa:** Você não está logado

**Solução:** O sino só aparece para usuários logados (admin/recepção)

---

### Problema: Som não toca

**Causa 1:** Som está mutado

**Solução:** Clique no botão 🔊 para desmutar

**Causa 2:** Navegador bloqueou áudio automático

**Solução:** Alguns navegadores bloqueiam áudio até o usuário interagir com a página. Clique em qualquer lugar da página uma vez.

**Causa 3:** Web Audio API não suportada

**Solução:** Use um navegador moderno (Chrome, Firefox, Edge, Safari)

---

### Problema: Notificações não chegam

**Causa 1:** Polling não está rodando

**Solução:** Abra o console do navegador (F12) e veja se há erros JavaScript

**Causa 2:** Endpoint `/notificacoes/api/notificacoes/nao-lidas` não responde

**Solução:** Verifique se o router de notificações está incluído no `main.py`

---

### Problema: Redirecionamento não funciona

**Causa:** Parâmetro `destaque` não está na URL

**Solução:** Verifique se o link da notificação está correto:
```
/agendamentos?data=2026-07-09&destaque=123
```

---

## 📊 Endpoints da API

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/notificacoes/api/notificacoes` | Lista notificações |
| GET | `/notificacoes/api/notificacoes/nao-lidas` | Conta não lidas |
| POST | `/notificacoes/api/notificacoes/{id}/ler` | Marca como lida |
| POST | `/notificacoes/api/notificacoes/ler-todas` | Marca todas como lidas |
| DELETE | `/notificacoes/api/notificacoes/{id}` | Exclui notificação |
| POST | `/notificacoes/api/notificacoes/limpar-antigas` | Limpa antigas |

---

## 🎯 Próximas Melhorias (Opcional)

1. **Notificações Push (PWA)**
   - Implementar Service Worker
   - Notificações mesmo com o site fechado
   - Requer HTTPS

2. **WebSocket (Tempo Real Verdadeiro)**
   - Substituir polling por WebSocket
   - Latência de milissegundos
   - Mais complexo de implementar

3. **Filtros Avançados**
   - Filtrar por tipo (agendamento, lembrete, etc)
   - Filtrar por data
   - Busca por texto

4. **Agrupamento de Notificações**
   - Agrupar notificações similares
   - Ex: "3 novos agendamentos"

5. **Marcação Automática como Lida**
   - Marcar como lida ao visualizar no dropdown
   - Não precisa clicar

---

## 📝 Resumo

✅ **Sistema completo de notificações in-app**
✅ **Tempo real via polling (3 segundos)**
✅ **Som de alerta (Web Audio API)**
✅ **Badge com contador**
✅ **Dropdown com lista**
✅ **Redirecionamento inteligente**
✅ **Destaque visual do agendamento**
✅ **Botão para mutar som**
✅ **Preferências salvas no navegador**

**O sistema está 100% funcional e pronto para uso!** 🚀

---

## 🚀 Deploy

Para aplicar no servidor:

```bash
# No seu PC (Windows)
git add .
git commit -m "feat: sistema completo de notificações em tempo real"
git push origin main

# No servidor (Linux)
cd ~/barbearia-automatica
git pull origin main
docker compose restart app
```

**Pronto!** O sistema de notificações estará ativo. 💈✨
