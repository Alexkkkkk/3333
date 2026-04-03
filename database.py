import asyncpg
import os
import json
import asyncio
from datetime import datetime, timedelta

async def init_db():
    """
    Инициализация сверхмощной архитектуры БД.
    Добавлена поддержка JSONB для хранения 'мыслей' ИИ.
    """
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    try:
        # Основная таблица действий ИИ
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS neural_mm_logs (
                id SERIAL PRIMARY KEY,
                cmd TEXT,
                amount FLOAT,
                urgency INT,
                reason TEXT,
                market_snapshot JSONB,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Индексы для мгновенного доступа на High-Load нагрузках
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON neural_mm_logs(timestamp)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_cmd ON neural_mm_logs(cmd)')
        
        print("✅ [DATABASE] Нейронная сеть подключена к Postgres Cluster.")
    finally:
        await conn.close()

async def get_market_state():
    """
    Собирает 'глаза' для ИИ. 
    Берет данные из истории и имитирует API DeDust.
    """
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    try:
        # Извлекаем последние 10 действий для глубокого анализа тренда
        history = await conn.fetch('''
            SELECT cmd, amount, reason, timestamp 
            FROM neural_mm_logs 
            ORDER BY timestamp DESC LIMIT 10
        ''')
        
        bot_memory = [
            {
                "action": h['cmd'],
                "amt": h['amount'],
                "reason": h['reason'],
                "time": h['timestamp'].strftime('%H:%M:%S')
            } for h in history
        ]

        # Эмуляция данных со смарт-контракта (здесь должна быть логика pytoniq)
        # ИИ будет использовать эти ключи для принятия решений
        return {
            "current_metrics": {
                "price_ton": 0.2854,
                "liquidity_ton": 15400.50,
                "volatility": "MODERATE",
                "trend": "UPWARD_PARABOLIC"
            },
            "recent_memory": bot_memory,
            "wallet_health": "OPTIMAL",
            "server_latency_ms": 45
        }
    finally:
        await conn.close()

async def log_ai_action(plan, current_context=None):
    """
    Логирует решение ИИ и прикрепляет к нему состояние рынка (Snapshot).
    """
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    try:
        await conn.execute(
            '''INSERT INTO neural_mm_logs (cmd, amount, urgency, reason, market_snapshot) 
               VALUES ($1, $2, $3, $4, $5)''', 
            plan.get('cmd', 'WAIT'), 
            float(plan.get('amt', 0)), 
            int(plan.get('urgency', 1)), 
            plan.get('reason', 'Neuro-pulse'),
            json.dumps(current_context) if current_context else None
        )
        
        # Оптимизация дискового пространства Bothost
        if os.getenv('DB_AUTO_OPTIMIZE') == 'true':
            await conn.execute("DELETE FROM neural_mm_logs WHERE timestamp < $1", 
                             datetime.now() - timedelta(days=5))
            
    except Exception as e:
        print(f"🚨 [DB_ERROR]: Не удалось записать импульс: {e}")
    finally:
        await conn.close()

async def get_stats_for_web():
    """
    Генерирует данные для твоего index.html.
    Твой дизайн logo.png и картинки будут дополнены этими цифрами.
    """
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    try:
        # 1. Общий объем прогнанных TON через ИИ
        total_vol = await conn.fetchval("SELECT SUM(amount) FROM neural_mm_logs")
        
        # 2. Последнее действие для статуса на главной
        last_action = await conn.fetchrow('''
            SELECT cmd, reason, timestamp 
            FROM neural_mm_logs 
            ORDER BY timestamp DESC LIMIT 1
        ''')
        
        # 3. Распределение команд (для круговой диаграммы)
        distribution = await conn.fetch('''
            SELECT cmd, COUNT(*) as count 
            FROM neural_mm_logs 
            GROUP BY cmd
        ''')

        # 4. Активность за последние 24 часа
        day_ago = datetime.now() - timedelta(days=1)
        daily_ops = await conn.fetchval("SELECT COUNT(*) FROM neural_mm_logs WHERE timestamp > $1", day_ago)

        return {
            "summary": {
                "total_ton": round(total_vol or 0, 2),
                "ops_24h": daily_ops or 0,
                "ai_status": "ONLINE_HYPER_DRIVE"
            },
            "latest": {
                "command": last_action['cmd'] if last_action else "IDLE",
                "reason": last_action['reason'] if last_action else "Waiting for signal",
                "time": last_action['timestamp'].strftime('%H:%M:%S') if last_action else "--:--:--"
            },
            "chart_data": {row['cmd']: row['count'] for row in distribution}
        }
    finally:
        await conn.close()
