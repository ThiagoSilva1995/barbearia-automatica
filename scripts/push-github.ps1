# =====================================================
# PUSH PARA GITHUB - AUTOMATIZADO
# =====================================================

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "PUSH PARA GITHUB" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar se .env esta no .gitignore
Write-Host "[1/6] Verificando seguranca do .env..." -ForegroundColor Yellow
if (Test-Path ".gitignore") {
    $gitignore = Get-Content ".gitignore"
    if ($gitignore -contains ".env") {
        Write-Host "OK: .env esta protegido no .gitignore" -ForegroundColor Green
    } else {
        Write-Host "AVISO: .env NAO esta no .gitignore! Adicionando..." -ForegroundColor Yellow
        Add-Content -Path ".gitignore" -Value ".env"
        Write-Host "OK: .env adicionado ao .gitignore" -ForegroundColor Green
    }
} else {
    Write-Host "ERRO: .gitignore nao encontrado! Criando..." -ForegroundColor Red
    ".env" | Out-File -FilePath ".gitignore" -Encoding utf8
}

Write-Host ""

# 2. Verificar mudancas
Write-Host "[2/6] Verificando mudancas..." -ForegroundColor Yellow
git status --short

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: Erro ao verificar git status. Voce esta na pasta correta?" -ForegroundColor Red
    exit 1
}

# Verificar se ha mudancas
$changes = git status --short
if (-not $changes) {
    Write-Host "INFO: Nenhuma mudanca para commitar." -ForegroundColor Gray
    $response = Read-Host "Deseja continuar mesmo assim? (s/n)"
    if ($response -ne "s") {
        Write-Host "Operacao cancelada." -ForegroundColor Red
        exit 0
    }
}

Write-Host ""

# 3. Verificar se .env nao esta nas mudancas
Write-Host "[3/6] Verificando se .env nao sera enviado..." -ForegroundColor Yellow
$envChanges = git status --short | Select-String ".env"
if ($envChanges) {
    Write-Host "ATENCAO: .env aparece nas mudancas!" -ForegroundColor Red
    Write-Host "Removendo .env do stage..." -ForegroundColor Yellow
    git restore --staged .env 2>$null
    git checkout -- .env 2>$null
    Write-Host "OK: .env removido com seguranca" -ForegroundColor Green
}

Write-Host ""

# 4. Adicionar mudancas
Write-Host "[4/6] Adicionando mudancas..." -ForegroundColor Yellow
git add .
Write-Host "OK: Mudancas adicionadas" -ForegroundColor Green

Write-Host ""

# 5. Criar commit
Write-Host "[5/6] Criando commit..." -ForegroundColor Yellow
$commitMsg = "fix: correcoes e melhorias no sistema

- Bugs corrigidos e otimizacao de UX
- Envio de WhatsApp em background
- Padronizacao de telefones
- Clean code e organizacao

#autocommit"

git commit -m $commitMsg

if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: Commit criado com sucesso" -ForegroundColor Green
} else {
    Write-Host "INFO: Nenhuma mudanca para commitar ou erro no commit" -ForegroundColor Gray
    $response = Read-Host "Deseja continuar com o push mesmo assim? (s/n)"
    if ($response -ne "s") {
        Write-Host "Operacao cancelada." -ForegroundColor Red
        exit 0
    }
}

Write-Host ""

# 6. Push para o GitHub
Write-Host "[6/6] Enviando para o GitHub..." -ForegroundColor Cyan
git push

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "PUSH CONCLUIDO COM SUCESSO!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Seu codigo esta seguro no GitHub!" -ForegroundColor Green
    Write-Host "https://github.com/ThiagoSilva1995/barbearia-automatica" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "ERRO NO PUSH!" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Possiveis causas:" -ForegroundColor Yellow
    Write-Host "  1. Token do GitHub expirou ou invalido" -ForegroundColor Gray
    Write-Host "  2. Sem conexao com a internet" -ForegroundColor Gray
    Write-Host "  3. Permissoes insuficientes no repositorio" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Tente novamente ou verifique suas credenciais." -ForegroundColor Yellow
    exit 1
}