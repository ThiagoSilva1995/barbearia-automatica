FROM python:3.11-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Instala dependências do sistema necessárias (compilador e libs do Postgres)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia o arquivo de requisitos e instala as bibliotecas Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o resto do código do projeto para o container
COPY . .

# Expõe a porta que o FastAPI usa
EXPOSE 8000

# Comando para iniciar o servidor
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
