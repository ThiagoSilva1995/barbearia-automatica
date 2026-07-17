"""
Script para adicionar ON DELETE CASCADE na foreign key de notificacoes.agendamento_id
Isso resolve o erro: "Key (id)=(X) is still referenced from table 'notificacoes'"
ao tentar deletar um agendamento.
"""
import os
import asyncio
from sqlalchemy import text
from app.database import engine

async def migrar():
    print("🔄 Iniciando migração de CASCADE DELETE em notificações...")
    
    # Nome da constraint padrão do PostgreSQL (pode variar, então vamos tentar descobrir ou usar o padrão)
    # O padrão do SQLAlchemy/Postgres é: {tabela}_{coluna}_fkey
    constraint_name = "notificacoes_agendamento_id_fkey"
    
    async with engine.begin() as conn:
        try:
            # 1. Verificar se a constraint existe
            check_query = text("""
                SELECT conname 
                FROM pg_constraint 
                WHERE conrelid = 'notificacoes'::regclass 
                AND confrelid = 'agendamentos'::regclass 
                AND conname = :constraint_name;
            """)
            result = await conn.execute(check_query, {"constraint_name": constraint_name})
            exists = result.fetchone()
            
            if exists:
                print(f"⚠️  Constraint '{constraint_name}' encontrada. Removendo...")
                # 2. Dropar a constraint antiga
                await conn.execute(text(f"ALTER TABLE notificacoes DROP CONSTRAINT {constraint_name};"))
                print("✅ Constraint antiga removida.")
            else:
                print("ℹ️  Constraint não encontrada com o nome padrão. Tentando encontrar...")
                # Tentar encontrar qualquer FK entre as tabelas
                find_fk = text("""
                    SELECT conname 
                    FROM pg_constraint 
                    WHERE conrelid = 'notificacoes'::regclass 
                    AND confrelid = 'agendamentos'::regclass;
                """)
                fk_result = await conn.execute(find_fk)
                fk_row = fk_result.fetchone()
                if fk_row:
                    constraint_name = fk_row[0]
                    print(f"🔍 Encontrada constraint: '{constraint_name}'. Removendo...")
                    await conn.execute(text(f"ALTER TABLE notificacoes DROP CONSTRAINT {constraint_name};"))
                    print("✅ Constraint antiga removida.")
                else:
                    print("⚠️  Nenhuma constraint de foreign key encontrada entre notificacoes e agendamentos.")
            
            # 3. Adicionar a nova constraint com ON DELETE CASCADE
            print("➕ Adicionando nova constraint com ON DELETE CASCADE...")
            await conn.execute(text("""
                ALTER TABLE notificacoes 
                ADD CONSTRAINT notificacoes_agendamento_id_fkey 
                FOREIGN KEY (agendamento_id) 
                REFERENCES agendamentos(id) 
                ON DELETE CASCADE;
            """))
            print("✅ Nova constraint adicionada com sucesso!")
            
            # 4. (Opcional) Limpar notificações órfãs que possam ter ficado
            print("🧹 Verificando e limpando notificações órfãs (se houver)...")
            await conn.execute(text("""
                DELETE FROM notificacoes 
                WHERE agendamento_id IS NOT NULL 
                AND agendamento_id NOT IN (SELECT id FROM agendamentos);
            """))
            print("✅ Limpeza concluída.")
            
            print("\n🎉 Migração concluída com sucesso! Agora você pode deletar agendamentos sem erros.")
            
        except Exception as e:
            print(f"❌ Erro durante a migração: {e}")
            print("💡 Dica: Você pode rodar este comando manualmente no banco Fly.io:")
            print("   flyctl postgres connect -a <seu-app-db>")
            print("   ALTER TABLE notificacoes DROP CONSTRAINT IF EXISTS notificacoes_agendamento_id_fkey;")
            print("   ALTER TABLE notificacoes ADD CONSTRAINT notificacoes_agendamento_id_fkey FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id) ON DELETE CASCADE;")

if __name__ == "__main__":
    asyncio.run(migrar())
