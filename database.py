import asyncpg
import os

async def init_db():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS neural_mm_logs (
            id SERIAL PRIMARY KEY,
            cmd TEXT,
            amount FLOAT,
            reason TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    await conn.close()

async def get_market_state():
    # Имитация сбора данных (в реальности - запрос к DeDust API)
    return {"price": 0.25, "trend": "up", "volatility": "low"}

async def log_ai_action(plan):
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    await conn.execute(
        'INSERT INTO neural_mm_logs (cmd, amount, reason) VALUES ($1, $2, $3)', 
        plan['cmd'], plan['amt'], plan['reason']
    )
    await conn.close()
