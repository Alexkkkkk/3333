import asyncpg
import os

DATABASE_URL = os.getenv('DATABASE_URL')

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS bot_logs (
            id SERIAL PRIMARY KEY,
            action_type TEXT,
            amount FLOAT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    await conn.close()

async def log_transaction(action, amount):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        'INSERT INTO bot_logs (action_type, amount) VALUES ($1, $2)',
        action, amount
    )
    await conn.close()
