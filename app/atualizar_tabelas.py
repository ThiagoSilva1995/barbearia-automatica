# app/atualizar_tabelas.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


async def atualizar_tabela_configuracoes(db: AsyncSession):
    try:
        colunas_esperadas = {
            "horario_inicio_manha": "VARCHAR DEFAULT '08:30'",
            "horario_fim_manha": "VARCHAR DEFAULT '11:00'",
            "horario_inicio_tarde": "VARCHAR DEFAULT '14:00'",
            "horario_fim_tarde": "VARCHAR DEFAULT '18:30'",
            "intervalo_minutos": "INTEGER DEFAULT 30",
            "admin_senha": "VARCHAR DEFAULT 'admin123'",
        }
        for coluna, definicao in colunas_esperadas.items():
            sql = text(
                f"ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS {coluna} {definicao}"
            )
            await db.execute(sql)
        await db.commit()
        logger.info("✅ Tabela 'configuracoes' verificada")
    except Exception as e:
        logger.error(f"❌ Erro em configuracoes: {e}")
        await db.rollback()
        raise


async def atualizar_tabela_agendamentos(db: AsyncSession):
    try:
        colunas_esperadas = {
            "is_confirmed": "BOOLEAN DEFAULT FALSE",
            "pago": "BOOLEAN DEFAULT FALSE",
            "observacoes": "TEXT",
            "duracao_minutos": "INTEGER DEFAULT 30",  # ← Para rastrear duração
        }
        for coluna, definicao in colunas_esperadas.items():
            sql = text(
                f"ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS {coluna} {definicao}"
            )
            await db.execute(sql)
        await db.commit()
        logger.info("✅ Tabela 'agendamentos' verificada")
    except Exception as e:
        logger.error(f"❌ Erro em agendamentos: {e}")
        await db.rollback()


async def atualizar_tabela_servicos(db: AsyncSession):
    try:
        sql = text(
            "ALTER TABLE servicos ADD COLUMN IF NOT EXISTS duracao_minutos INTEGER DEFAULT 30"
        )
        await db.execute(sql)
        await db.commit()
        logger.info("✅ Tabela 'servicos' atualizada")
    except Exception as e:
        logger.error(f"❌ Erro em servicos: {e}")
        await db.rollback()
        raise


async def executar_migracoes(db: AsyncSession):
    logger.info("🔄 Iniciando migrações...")
    await atualizar_tabela_configuracoes(db)
    await atualizar_tabela_agendamentos(db)
    await atualizar_tabela_servicos(db)
    logger.info("✅ Migrações concluídas!")
