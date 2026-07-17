"""
Script de migração para adicionar colunas faltantes na tabela notificacoes
Execute este script uma vez para atualizar o banco de dados
"""
import asyncio
from sqlalchemy import text
from app.database import engine


async def migrar_tabela_notificacoes():
    """Adiciona colunas faltantes na tabela notificacoes"""
    
    print("🔄 Iniciando migração da tabela notificacoes...")
    
    # Lista de colunas para adicionar (nome, tipo_sql, default)
    colunas_para_adicionar = [
        ("cor", "VARCHAR(20)", "'red'"),
        ("link", "VARCHAR(500)", "NULL"),
        ("agendamento_id", "INTEGER", "NULL"),
        ("data_agendamento", "VARCHAR(10)", "NULL"),
        ("lida_em", "TIMESTAMP WITH TIME ZONE", "NULL"),
        ("dados_extra", "TEXT", "NULL"),
    ]
    
    async with engine.begin() as conn:
        # Verificar quais colunas já existem
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'notificacoes'
        """))
        colunas_existentes = [row[0] for row in result.fetchall()]
        
        print(f"📋 Colunas existentes: {colunas_existentes}")
        
        # Adicionar colunas que não existem
        for nome_coluna, tipo_sql, default in colunas_para_adicionar:
            if nome_coluna not in colunas_existentes:
                print(f"➕ Adicionando coluna: {nome_coluna} ({tipo_sql})")
                sql = f"ALTER TABLE notificacoes ADD COLUMN {nome_coluna} {tipo_sql} DEFAULT {default}"
                await conn.execute(text(sql))
                print(f"✅ Coluna {nome_coluna} adicionada!")
            else:
                print(f"✓ Coluna {nome_coluna} já existe")
        
        # Verificar se a constraint da foreign key existe
        result = await conn.execute(text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'notificacoes' 
            AND constraint_type = 'FOREIGN KEY'
        """))
        constraints = [row[0] for row in result.fetchall()]
        
        if not any('agendamento_id' in c for c in constraints):
            print("➕ Adicionando foreign key para agendamento_id...")
            try:
                await conn.execute(text("""
                    ALTER TABLE notificacoes 
                    ADD CONSTRAINT fk_notificacao_agendamento 
                    FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id)
                """))
                print("✅ Foreign key adicionada!")
            except Exception as e:
                print(f"⚠️ Aviso ao adicionar FK: {e}")
        else:
            print("✓ Foreign key já existe")
    
    print("✅ Migração concluída com sucesso!")


if __name__ == "__main__":
    asyncio.run(migrar_tabela_notificacoes())
