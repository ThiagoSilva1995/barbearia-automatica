# 👑 Guia do Super Admin (Acesso de Desenvolvedor)

## 🎯 O que é o Super Admin?

O **Super Admin** é um usuário especial com acesso total ao sistema, independente da senha configurada pelo administrador local. Ideal para:

- ✅ Desenvolvedor/dono do software
- ✅ Suporte técnico
- ✅ Acesso de emergência
- ✅ Visualizar qualquer barbearia sem precisar da senha do admin local

---

## 🔧 Como Configurar no Servidor

### Passo 1: Adicionar a Variável de Ambiente

No servidor, edite o arquivo `.env`:

```bash
nano .env
```

Adicione a linha:

```env
SUPER_ADMIN_PASSWORD=SuaSenhaSuperForte123!
```

**Exemplo:**
```env
# Banco de Dados
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db

# Sistema
SECRET_KEY=sua_chave_secreta

# Super Admin (Desenvolvedor)
SUPER_ADMIN_PASSWORD=Thales@Dev2026!
```

**⚠️ IMPORTANTE:**
- Use uma senha **forte** (mínimo 12 caracteres)
- Combine letras maiúsculas, minúsculas, números e símbolos
- **NÃO** use senhas óbvias como "admin123" ou "super123"
- Esta senha é **diferente** da senha do admin local

---

### Passo 2: Reiniciar o Container

```bash
docker compose restart app
```

Ou reconstruir completamente:

```bash
docker compose up -d --build app
```

---

### Passo 3: Fazer Login como Super Admin

1. Acesse: `http://seu-servidor.com/login`
2. Digite a **senha do Super Admin** (a que você configurou no `.env`)
3. Clique em "Entrar"
4. Você verá o badge **👑 Super Admin** no canto superior direito

---

## 🔐 Diferença entre Admin e Super Admin

| Característica | Admin Local | Super Admin |
|----------------|-------------|-------------|
| **Senha** | Configurada no banco ou `.env` | Configurada apenas no `.env` |
| **Quem configura** | Administrador da barbearia | Desenvolvedor/dono do sistema |
| **Acesso** | Total na barbearia | Total em todas as barbearias |
| **Pode ser alterado** | Sim, pelo painel admin | Não, apenas via `.env` |
| **Indicador visual** | "Administrador" | "👑 Super Admin" |
| **Uso** | Gestão diária | Suporte, emergência, desenvolvimento |

---

## 🛡️ Segurança

### Boas Práticas

1. **Senha Forte:**
   - Mínimo 12 caracteres
   - Combine: maiúsculas + minúsculas + números + símbolos
   - Exemplo: `Thales@Dev2026!Xyz`

2. **Não Compartilhe:**
   - A senha do Super Admin é **secreta**
   - Apenas o desenvolvedor/dono do sistema deve saber

3. **Arquivo `.env` Protegido:**
   - O `.env` **NÃO** deve ser commitado no Git
   - Já está no `.gitignore` por padrão
   - Apenas o servidor deve ter acesso

4. **Troca de Senha:**
   - Para trocar, edite o `.env` e reinicie o container
   - Não há interface para trocar (proposital, por segurança)

---

## 📋 Exemplo Prático

### Cenário: Você precisa acessar o sistema de um cliente

**Situação:** Um cliente reportou um problema e você precisa verificar o sistema dele, mas não sabe a senha do admin.

**Solução:**

1. Acesse o servidor via SSH:
   ```bash
   ssh usuario@servidor.com
   ```

2. Navegue até a pasta do projeto:
   ```bash
   cd ~/barbearia-automatica
   ```

3. Veja a senha do Super Admin:
   ```bash
   grep SUPER_ADMIN_PASSWORD .env
   ```

4. Copie a senha e acesse o sistema:
   ```
   http://cliente.barbearia.com/login
   ```

5. Digite a senha do Super Admin e faça login

6. Você terá acesso total com o badge **👑 Super Admin**

---

## 🚨 Acesso de Emergência

Se você **esqueceu a senha do Super Admin**:

1. Acesse o servidor via SSH
2. Edite o `.env`:
   ```bash
   nano .env
   ```
3. Altere a linha:
   ```env
   SUPER_ADMIN_PASSWORD=NovaSenhaForte123!
   ```
4. Reinicie o container:
   ```bash
   docker compose restart app
   ```
5. Use a nova senha para fazer login

---

## 📊 Permissões do Super Admin

O Super Admin tem **todas as permissões** do Admin Local, incluindo:

- ✅ Ver todos os agendamentos
- ✅ Criar/editar/cancelar agendamentos
- ✅ Cadastrar clientes, barbeiros, serviços, produtos
- ✅ Configurações do sistema
- ✅ Relatórios e estatísticas
- ✅ Bloqueios e feriados
- ✅ Fila inteligente
- ✅ Notificações

**Diferença:** O Super Admin **não pode** ser removido ou ter suas permissões alteradas pelo admin local.

---

## 🎨 Indicador Visual

Quando logado como Super Admin, você verá:

- **Badge:** 👑 Super Admin (roxo) no canto superior direito
- **Nome:** "Super Admin" no header
- **Menu:** Acesso completo a todas as opções

---

## 🔍 Verificar se Está Funcionando

### Teste 1: Verificar a Variável

No servidor:
```bash
grep SUPER_ADMIN_PASSWORD .env
```

Deve mostrar:
```
SUPER_ADMIN_PASSWORD=SuaSenhaAqui
```

### Teste 2: Fazer Login

1. Acesse: `http://seu-servidor.com/login`
2. Digite a senha do Super Admin
3. Deve logar com sucesso
4. Deve ver o badge **👑 Super Admin**

### Teste 3: Verificar Permissões

1. Faça login como Super Admin
2. Tente acessar:
   - `/servicos` ✅
   - `/produtos` ✅
   - `/admin/configuracoes` ✅
   - `/admin/bloqueios` ✅
   - `/estatisticas` ✅

Todos devem estar acessíveis.

---

## 📝 Resumo

| Item | Descrição |
|------|-----------|
| **O que é** | Acesso de desenvolvedor/dono do sistema |
| **Como configurar** | Adicionar `SUPER_ADMIN_PASSWORD` no `.env` |
| **Como usar** | Fazer login com a senha configurada |
| **Indicador** | Badge 👑 Super Admin (roxo) |
| **Permissões** | Total (todas as funções do admin) |
| **Segurança** | Senha forte, não compartilhar, `.env` protegido |

---

## 🆘 Problemas Comuns

### Problema: Não consigo fazer login com Super Admin

**Solução:**
1. Verifique se a variável está no `.env`:
   ```bash
   grep SUPER_ADMIN_PASSWORD .env
   ```
2. Reinicie o container:
   ```bash
   docker compose restart app
   ```
3. Verifique os logs:
   ```bash
   docker compose logs app
   ```

### Problema: Esqueci a senha do Super Admin

**Solução:**
1. Acesse o servidor via SSH
2. Edite o `.env` e altere a senha
3. Reinicie o container
4. Use a nova senha

### Problema: O badge não aparece

**Solução:**
1. Faça logout e login novamente
2. Limpe o cache do navegador (Ctrl+F5)
3. Verifique se está usando a senha correta

---

## 🎯 Conclusão

O Super Admin é uma ferramenta poderosa para:

- ✅ Desenvolvedores acessarem o sistema para suporte
- ✅ Donos do software visualizarem qualquer instalação
- ✅ Acesso de emergência sem depender do admin local
- ✅ Testes e desenvolvimento

**Use com responsabilidade e mantenha a senha segura!** 🔐

---

**Criado em:** 09/07/2026  
**Versão:** 1.0  
**Status:** ✅ Funcionando
