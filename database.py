import asyncpg
import os

async def init_db():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS market_dominance (
            id SERIAL PRIMARY KEY,
            action_type TEXT,
            amount FLOAT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    await conn.close()

async def log_market_action(action, amount):
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    await conn.execute(
        'INSERT INTO market_dominance (action_type, amount) VALUES ($1, $2)', 
        action, amount
    )
    await conn.close()
