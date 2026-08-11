"""Script para criar a tabela de auditoria no banco de produção"""
import asyncio
from app.database import engine, Base
from app.models.auditoria import AuditoriaAgendamento


async def main():
    print("🔄 Criando tabela de auditoria...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tabela 'auditoria_agendamentos' criada com sucesso!")


if __name__ == "__main__":
    asyncio.run(main())
