# 📚 Documentação da API - Barbearia do Thales

## 🚀 Acesso à Documentação Interativa

O sistema possui **documentação automática e interativa** disponível em múltiplos formatos:

### 1. **Swagger UI** (Recomendado)
- **URL**: http://localhost:8000/docs
- **Características**: 
  - Interface interativa
  - Teste de endpoints diretamente do navegador
  - Validação de schemas
  - Exemplos de request/response

### 2. **ReDoc**
- **URL**: http://localhost:8000/redoc
- **Características**:
  - Documentação em formato de página única
  - Navegação por seções
  - Visualização mais limpa

### 3. **OpenAPI JSON**
- **URL**: http://localhost:8000/openapi.json
- **Características**:
  - Schema completo em JSON
  - Para integração com outras ferramentas
  - Geração de clientes SDK

---

## 📋 Endpoints da API REST

### 👤 Clientes (`/api/clientes`)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/api/clientes/` | Listar todos os clientes |
| `GET` | `/api/clientes/{id}` | Buscar cliente por ID |
| `GET` | `/api/clientes/telefone/{telefone}` | Buscar por telefone |
| `GET` | `/api/clientes/aniversariantes/{mes}/{dia}` | Aniversariantes do dia |
| `POST` | `/api/clientes/` | Criar novo cliente |
| `PUT` | `/api/clientes/{id}` | Atualizar cliente |
| `DELETE` | `/api/clientes/{id}` | Excluir cliente |
| `PATCH` | `/api/clientes/{id}/aniversario` | Marcar aniversário enviado |

### 📅 Agendamentos (`/api/agendamentos`)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/api/agendamentos/` | Listar agendamentos (com filtros) |
| `GET` | `/api/agendamentos/{id}` | Buscar agendamento por ID |
| `GET` | `/api/agendamentos/cliente/{cliente_id}` | Agendamentos de um cliente |
| `GET` | `/api/agendamentos/barbeiro/{barbeiro_id}` | Agendamentos de um barbeiro |
| `GET` | `/api/agendamentos/hoje` | Agendamentos de hoje |
| `GET` | `/api/agendamentos/semana` | Agendamentos da semana |
| `POST` | `/api/agendamentos/` | Criar novo agendamento |
| `PUT` | `/api/agendamentos/{id}` | Atualizar agendamento |
| `DELETE` | `/api/agendamentos/{id}` | Cancelar agendamento |
| `POST` | `/api/agendamentos/{id}/pagar` | Confirmar pagamento |

---

## 🧪 Exemplos de Uso

### Exemplo 1: Listar Clientes

```bash
curl -X GET "http://localhost:8000/api/clientes/?limit=10"
```

**Resposta:**
```json
[
  {
    "id": 1,
    "nome": "João Silva",
    "telefone": "5573999999999",
    "data_nascimento": "1990-05-15",
    "parabens_enviado": false
  }
]
```

### Exemplo 2: Criar Cliente

```bash
curl -X POST "http://localhost:8000/api/clientes/" \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "Maria Santos",
    "telefone": "73988887777",
    "data_nascimento": "1995-08-20"
  }'
```

### Exemplo 3: Criar Agendamento

```bash
curl -X POST "http://localhost:8000/api/agendamentos/" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente_id": 1,
    "barbeiro_id": 1,
    "data": "2026-07-10",
    "hora": "14:30",
    "servico_ids": [1, 2]
  }'
```

### Exemplo 4: Buscar Aniversariantes

```bash
curl -X GET "http://localhost:8000/api/clientes/aniversariantes/7/9"
```

**Resposta:** Clientes que fazem aniversário em 9 de julho

---

## 🔍 Filtros e Paginação

### Paginação
```bash
# Pular primeiros 10 e retornar próximos 20
GET /api/clientes/?skip=10&limit=20
```

### Filtros de Agendamentos
```bash
# Agendamentos de uma data específica
GET /api/agendamentos/?data=2026-07-10

# Agendamentos de um barbeiro
GET /api/agendamentos/?barbeiro_id=1

# Apenas agendamentos pagos
GET /api/agendamentos/?pago=true

# Combinando filtros
GET /api/agendamentos/?data=2026-07-10&barbeiro_id=1&pago=false
```

---

## 📊 Códigos de Status HTTP

| Código | Significado | Descrição |
|--------|-------------|-----------|
| `200` | OK | Requisição bem-sucedida |
| `201` | Created | Recurso criado com sucesso |
| `204` | No Content | Requisição bem-sucedida sem conteúdo (ex: DELETE) |
| `400` | Bad Request | Dados inválidos na requisição |
| `404` | Not Found | Recurso não encontrado |
| `409` | Conflict | Conflito (ex: horário já ocupado) |
| `422` | Unprocessable Entity | Erro de validação |
| `500` | Internal Server Error | Erro interno do servidor |

---

## 🔐 Autenticação

### Área Pública (Cliente)
- **Sem autenticação necessária**
- Acesso via telefone
- Endpoints: `/cliente/*`

### Área Administrativa
- **Requer login com senha**
- Session-based authentication
- Endpoints: `/home`, `/agendamentos`, `/configuracoes`, etc.

### API REST
- **Atualmente sem autenticação** (pode ser adicionada no futuro)
- Endpoints: `/api/*`

---

## 🛠️ Ferramentas Úteis

### 1. **Postman**
- Importe o OpenAPI JSON: http://localhost:8000/openapi.json
- Teste todos os endpoints com interface gráfica

### 2. **Insomnia**
- Similar ao Postman
- Importe o schema OpenAPI

### 3. **curl**
```bash
# Listar clientes
curl http://localhost:8000/api/clientes/

# Criar cliente
curl -X POST http://localhost:8000/api/clientes/ \
  -H "Content-Type: application/json" \
  -d '{"nome":"Teste","telefone":"73999999999","data_nascimento":"2000-01-01"}'
```

### 4. **Python (requests)**
```python
import requests

# Listar clientes
response = requests.get("http://localhost:8000/api/clientes/")
clientes = response.json()

# Criar agendamento
data = {
    "cliente_id": 1,
    "barbeiro_id": 1,
    "data": "2026-07-10",
    "hora": "14:30",
    "servico_ids": [1, 2]
}
response = requests.post("http://localhost:8000/api/agendamentos/", json=data)
```

---

## 📝 Schemas Pydantic

### Cliente

**ClienteCreate:**
```json
{
  "nome": "string (min 3 caracteres)",
  "telefone": "string (10-15 dígitos)",
  "data_nascimento": "date (YYYY-MM-DD)"
}
```

**ClienteResponse:**
```json
{
  "id": 1,
  "nome": "João Silva",
  "telefone": "5573999999999",
  "data_nascimento": "1990-05-15",
  "parabens_enviado": false
}
```

### Agendamento

**AgendamentoCreate:**
```json
{
  "cliente_id": 1,
  "barbeiro_id": 1,
  "data": "2026-07-10",
  "hora": "14:30",
  "servico_ids": [1, 2],
  "produto_ids": [],
  "duracao_minutos": 60
}
```

**AgendamentoResponse:**
```json
{
  "id": 1,
  "cliente_id": 1,
  "barbeiro_id": 1,
  "data": "2026-07-10",
  "hora": "14:30:00",
  "servico_ids": [1, 2],
  "produto_ids": [],
  "pago": false,
  "is_confirmed": false,
  "duracao_minutos": 60
}
```

---

## 🚨 Tratamento de Erros

Todos os endpoints retornam erros no formato:

```json
{
  "detail": "Mensagem descritiva do erro"
}
```

**Exemplos:**

```json
// 404 Not Found
{
  "detail": "Cliente com ID 999 não encontrado"
}

// 409 Conflict
{
  "detail": "Horário indisponível: já existe um agendamento neste horário"
}

// 400 Bad Request
{
  "detail": "Já existe um cliente cadastrado com o telefone 5573999999999"
}
```

---

## 🔄 Integração com Frontend

### JavaScript (Fetch API)
```javascript
// Listar clientes
fetch('http://localhost:8000/api/clientes/')
  .then(response => response.json())
  .then(clientes => console.log(clientes));

// Criar agendamento
fetch('http://localhost:8000/api/agendamentos/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    cliente_id: 1,
    barbeiro_id: 1,
    data: '2026-07-10',
    hora: '14:30',
    servico_ids: [1, 2]
  })
})
.then(response => response.json())
.then(data => console.log(data));
```

---

## 📞 Suporte

Para dúvidas sobre a API:
- **Documentação Interativa**: http://localhost:8000/docs
- **Schema OpenAPI**: http://localhost:8000/openapi.json
- **Email**: contato@barberiathales.com.br

---

**Última atualização**: Julho de 2026  
**Versão da API**: 1.0.0
