# 🎯 Guia de Uso do Swagger UI - Barbearia do Thales

## 📍 Acessando o Swagger

1. **Inicie o sistema:**
   ```bash
   docker compose up -d
   ```

2. **Abra o navegador:**
   ```
   http://localhost:8000/docs
   ```

3. **Você verá a interface do Swagger UI** com todos os endpoints organizados por tags.

---

## 🎨 Entendendo a Interface

### Estrutura da Página

```
┌─────────────────────────────────────────────────┐
│  🏪 Barbearia do Thales - API  [v1.0.0]         │
├─────────────────────────────────────────────────┤
│  [👤 Clientes]  [📅 Agendamentos]  [🔧 Sistema] │
├─────────────────────────────────────────────────┤
│  GET  /api/clientes/                            │
│  POST /api/clientes/                            │
│  GET  /api/clientes/{cliente_id}                │
│  ...                                            │
└─────────────────────────────────────────────────┘
```

### Tags (Categorias)

Os endpoints estão organizados em tags coloridas:

- **👤 Clientes** - Operações com clientes
- **📅 Agendamentos** - Operações com agendamentos
- **🔧 Sistema** - Endpoints do sistema (health check, etc)

---

## 🧪 Testando Endpoints

### Exemplo 1: Listar Clientes

1. **Clique na tag "👤 Clientes"**
2. **Clique em `GET /api/clientes/`**
3. **Clique no botão "Try it out"** (canto superior direito)
4. **Ajuste os parâmetros** (opcional):
   - `skip`: 0 (pular primeiros registros)
   - `limit`: 10 (máximo de registros)
5. **Clique no botão "Execute"**
6. **Veja o resultado** na seção "Responses"

**Resposta esperada:**
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

---

### Exemplo 2: Criar um Cliente

1. **Clique em `POST /api/clientes/`**
2. **Clique em "Try it out"**
3. **Edite o corpo da requisição** (Request body):
   ```json
   {
     "nome": "Maria Santos",
     "telefone": "73988887777",
     "data_nascimento": "1995-08-20"
   }
   ```
4. **Clique em "Execute"**
5. **Veja a resposta** com status 201 Created

**Resposta esperada:**
```json
{
  "id": 2,
  "nome": "Maria Santos",
  "telefone": "5573988887777",
  "data_nascimento": "1995-08-20",
  "parabens_enviado": false
}
```

---

### Exemplo 3: Buscar Aniversariantes

1. **Clique em `GET /api/clientes/aniversariantes/{mes}/{dia}`**
2. **Clique em "Try it out"**
3. **Preencha os parâmetros**:
   - `mes`: 7 (julho)
   - `dia`: 9 (dia 9)
4. **Clique em "Execute"**
5. **Veja a lista de aniversariantes**

---

### Exemplo 4: Criar Agendamento

1. **Clique em `POST /api/agendamentos/`**
2. **Clique em "Try it out"**
3. **Edite o corpo da requisição**:
   ```json
   {
     "cliente_id": 1,
     "barbeiro_id": 1,
     "data": "2026-07-10",
     "hora": "14:30",
     "servico_ids": [1, 2],
     "produto_ids": []
   }
   ```
4. **Clique em "Execute"**
5. **Se houver conflito**, você verá erro 409
6. **Se sucesso**, verá o agendamento criado

---

## 🔍 Usando Filtros

### Filtrar Agendamentos por Data

1. **Clique em `GET /api/agendamentos/`**
2. **Clique em "Try it out"**
3. **Preencha os parâmetros**:
   - `data`: 2026-07-10
   - `barbeiro_id`: (deixe vazio para todos)
   - `pago`: (deixe vazio para todos)
4. **Clique em "Execute"**

### Paginação

1. **Use `skip` e `limit`**:
   - `skip`: 10 (pula primeiros 10)
   - `limit`: 20 (retorna próximos 20)

---

## 📊 Entendendo as Respostas

### Códigos de Status

| Código | Cor | Significado |
|--------|-----|-------------|
| 200 | 🟢 Verde | Sucesso |
| 201 | 🟢 Verde | Criado com sucesso |
| 204 | 🟢 Verde | Sucesso sem conteúdo |
| 400 | 🔴 Vermelho | Dados inválidos |
| 404 | 🟡 Amarelo | Não encontrado |
| 409 | 🟠 Laranja | Conflito |
| 500 | 🔴 Vermelho | Erro interno |

### Formato de Erro

```json
{
  "detail": "Mensagem descritiva do erro"
}
```

---

## 🛠️ Dicas Avançadas

### 1. **Download da Especificação OpenAPI**

No topo da página, clique em:
- **`/openapi.json`** - Schema completo em JSON

Você pode usar este arquivo para:
- Importar no Postman
- Gerar clientes SDK automaticamente
- Integrar com outras ferramentas

### 2. **Autorização (Futuro)**

Se autenticação for adicionada:
1. Clique no botão **"Authorize"** (🔒) no topo
2. Insira o token/API key
3. Todas as requisições incluirão automaticamente

### 3. **Schemas (Modelos)**

No final da página, veja a seção **"Schemas"**:
- Mostra a estrutura de todos os modelos
- Cliente, Agendamento, etc.
- Útil para entender os campos obrigatórios

---

## 🎯 Casos de Uso Comuns

### Caso 1: Verificar Agenda do Dia

```bash
1. GET /api/agendamentos/hoje
2. Veja todos os agendamentos de hoje
3. Organize a agenda da barbearia
```

### Caso 2: Buscar Cliente por Telefone

```bash
1. GET /api/clientes/telefone/{telefone}
2. Digite: 73999999999
3. Veja se o cliente já está cadastrado
```

### Caso 3: Confirmar Pagamento

```bash
1. POST /api/agendamentos/{id}/pagar
2. Informe:
   - servico_ids: [1, 2]
   - produtos_qtd: {"1": 1, "2": 2}
3. Sistema marca como pago e baixa estoque
```

### Caso 4: Enviar Mensagem de Aniversário

```bash
1. GET /api/clientes/aniversariantes/7/9
2. Veja quem faz aniversário hoje
3. Envie mensagens personalizadas
4. PATCH /api/clientes/{id}/aniversario?enviado=true
5. Marca como enviado (evita spam)
```

---

## 🐛 Troubleshooting

### Problema: "Failed to fetch"

**Causa**: Sistema não está rodando

**Solução**:
```bash
docker compose up -d
```

### Problema: "404 Not Found"

**Causa**: Recurso não existe

**Solução**: Verifique se o ID está correto

### Problema: "409 Conflict"

**Causa**: Horário já ocupado

**Solução**: Escolha outro horário ou barbeiro

### Problema: "422 Unprocessable Entity"

**Causa**: Dados inválidos

**Solução**: Verifique o formato dos dados (ex: data no formato YYYY-MM-DD)

---

## 📚 Recursos Adicionais

### Documentação Alternativa

- **ReDoc**: http://localhost:8000/redoc
  - Visualização mais limpa
  - Navegação por seções

### Schema OpenAPI

- **JSON**: http://localhost:8000/openapi.json
  - Para integração com outras ferramentas

### README da API

- **Arquivo**: `API_DOCUMENTATION.md`
  - Exemplos completos
  - Casos de uso
  - Integração com frontend

---

## 🎉 Próximos Passos

1. ✅ **Explore todos os endpoints** no Swagger UI
2. ✅ **Teste criando clientes e agendamentos**
3. ✅ **Use os filtros** para buscar dados específicos
4. ✅ **Integre com seu frontend** usando os schemas
5. ✅ **Automatize testes** com as ferramentas mencionadas

---

**Dúvidas?** Consulte a documentação completa em `API_DOCUMENTATION.md`

**Bom uso!** 🚀
