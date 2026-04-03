import asyncpg
import os
import asyncio
from datetime import datetime, timedelta

async def init_db():
    """
    Инициализация расширенной структуры таблиц для обучения ИИ.
    """
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    try:
        # Таблица логов команд ИИ
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS neural_mm_logs (
                id SERIAL PRIMARY KEY,
                cmd TEXT,
                amount FLOAT,
                urgency INT,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Индекс для ускорения выборки последних состояний рынка
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON neural_mm_logs(timestamp)')
        
        print("✅ [DB_INIT] Структура данных синхронизирована.")
    finally:
        await conn.close()

async def get_market_state():
    """
    Генерирует глубокий контекст для ИИ. 
    В реальном сценарии здесь должен быть fetch к DeDust API /stonfi.
    """
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    try:
        # Получаем историю последних 5 действий для анализа 'памяти' бота
        recent_history = await conn.fetch('''
            SELECT cmd, amount, timestamp FROM neural_mm_logs 
            ORDER BY timestamp DESC LIMIT 5
        ''')
        
        history_summary = [
            f"{row['cmd']} ({row['amount']} TON) at {row['timestamp'].strftime('%H:%M')}" 
            for row in recent_history
        ]

        # Имитация живых данных с DeDust (замени на реальный запрос к SDK/API)
        # Здесь ИИ видит тренд и волатильность
        return {
            "market_info": {
                "current_price_ton": 0.285,
                "liquidity_depth": "MEDIUM",
                "volatility_24h": "12.4%",
                "trend_phase": "CONSOLIDATION", # Накопление перед рывком
                "sell_wall_distance": "4.2%"    # Расстояние до крупного ордера на продажу
            },
            "bot_memory": history_summary,
            "wallet_status": "READY",
            "system_load": "OPTIMAL"
        }
    finally:
        await conn.close()

async def log_ai_action(plan):
    """
    Сохранение принятого решения ИИ с полным набором метаданных.
    """
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    try:
        await conn.execute(
            '''INSERT INTO neural_mm_logs (cmd, amount, urgency, reason) 
               VALUES ($1, $2, $3, $4)''', 
            plan.get('cmd', 'WAIT'), 
            float(plan.get('amt', 0)), 
            int(plan.get('urgency', 1)), 
            plan.get('reason', 'Routine operation')
        )
        
        # Авто-очистка старых логов (старше 7 дней), чтобы база Bothost летала
        if os.getenv('DB_AUTO_OPTIMIZE') == 'true':
            await conn.execute("DELETE FROM neural_mm_logs WHERE timestamp < $1", 
                             datetime.now() - timedelta(days=7))
            
    except Exception as e:
        print(f"🚨 [DB_WRITE_ERROR]: {e}")
    finally:
        await conn.close()

async def get_stats_for_web():
    """
    Специальная функция для твоего index.html (Dashboard).
    Возвращает данные для графиков и статус ИИ.
    """
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    try:
        total_vol = await conn.fetchval("SELECT SUM(amount) FROM neural_mm_logs")
        last_action = await conn.fetchrow("SELECT * FROM neural_mm_logs ORDER BY timestamp DESC LIMIT 1")
        
        return {
            "total_pushed_ton": total_vol or 0,
            "last_decision": last_action['reason'] if last_action else "Waiting for start",
            "active_mode": "NEURAL_DOMINATION"
        }
    finally:
        await conn.close()
