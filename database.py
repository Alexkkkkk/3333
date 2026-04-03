import asyncpg
import os

async def init_db():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS neural_growth_metrics (
            id SERIAL PRIMARY KEY,
            pulse_type TEXT,
            amount FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    await conn.close()

async def log_pulse_action(p_type, amount):
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    await conn.execute(
        'INSERT INTO neural_growth_metrics (pulse_type, amount) VALUES ($1, $2)', 
        p_type, amount
    )
    await conn.close()
