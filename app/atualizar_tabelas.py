import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, Base
from app.models.configuracao import Configuracao  # Importa o modelo atualizado


async def atualizar_estrutura():
    print("🔨 Conectando ao banco para atualizar estruturas...")
    async with engine.begin() as conn:
        # O create_all é inteligente: ele cria tabelas que faltam e ignora as que já existem
        # MAS ele não adiciona colunas novas em tabelas existentes no PostgreSQL por padrão.
        # Para resolver isso sem migradores complexos (Alembic), vamos usar um truque seguro:

        # 1. Criar todas as tabelas (garante que novas existam)
        await conn.run_sync(Base.metadata.create_all)

        # 2. Verificar se a coluna falta e adicionar manualmente se necessário
        # Isso é necessário porque o PostgreSQL é rígido com alterações de schema
        from sqlalchemy import text

        try:
            # Tenta selecionar a coluna nova. Se falhar, ela não existe.
            await conn.execute(
                text("SELECT horario_inicio_manha FROM configuracoes LIMIT 1")
            )
            print("✅ Colunas de horário já existem.")
        except Exception:
            print("⚠️ Colunas de horário não encontradas. Adicionando agora...")
            # Adiciona as colunas que faltam no modelo Configuracao
            await conn.execute(
                text(
                    "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS horario_inicio_manha VARCHAR DEFAULT '08:30'"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS horario_fim_manha VARCHAR DEFAULT '11:00'"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS horario_inicio_tarde VARCHAR DEFAULT '14:00'"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS horario_fim_tarde VARCHAR DEFAULT '18:30'"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS intervalo_minutos INTEGER DEFAULT 30"
                )
            )
            print("✅ Colunas adicionadas com sucesso!")

    print("🎉 Estrutura do banco atualizada!")


if __name__ == "__main__":
    asyncio.run(atualizar_estrutura())
