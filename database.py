import asyncpg
import os
import json
import asyncio
from datetime import datetime, timedelta

# Глобальный пул соединений
_pool = None

async def get_pool():
    """Создает пул соединений с High-Load лимитами (Bothost Optimized)."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            os.getenv('DATABASE_URL'),
            min_size=10,
            max_size=50,
            command_timeout=60,
            max_queries=100000,
            max_inactive_connection_lifetime=300.0
        )
    return _pool

async def init_db():
    """Инициализация архитектуры: Логи, Финансы и Динамические настройки."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 1. ТАБЛИЦА НАСТРОЕК (Управление процентами)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS distribution_settings (
                id SERIAL PRIMARY KEY,
                label TEXT UNIQUE,
                holders_pct FLOAT,
                staking_pct FLOAT,
                liquidity_pct FLOAT,
                treasury_pct FLOAT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Дефолтный пресет (2% / 30% / 38% / 30%)
        await conn.execute('''
            INSERT INTO distribution_settings (label, holders_pct, staking_pct, liquidity_pct, treasury_pct)
            VALUES ('default', 0.02, 0.30, 0.38, 0.30)
            ON CONFLICT (label) DO NOTHING
        ''')

        # 2. ОСНОВНАЯ ТАБЛИЦА ЛОГОВ ТОРГОВЛИ
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS neural_mm_logs (
                id SERIAL PRIMARY KEY,
                cmd TEXT NOT NULL,
                amount FLOAT DEFAULT 0.0,
                urgency INT DEFAULT 1,
                reason TEXT,
                market_snapshot JSONB,
                performance_metrics JSONB,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 3. ТАБЛИЦА ФАКТИЧЕСКОГО РАСПРЕДЕЛЕНИЯ ПРИБЫЛИ
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS profit_distribution (
                id SERIAL PRIMARY KEY,
                total_amount FLOAT NOT NULL,
                holders_share FLOAT,
                staking_share FLOAT,
                liquidity_share FLOAT,
                treasury_share FLOAT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Индексы для Ultra Fast Performance
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp_desc ON neural_mm_logs(timestamp DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_cmd_lookup ON neural_mm_logs(cmd)')
        
        print("✅ [DATABASE] Система Neural Pulse V28 (Dynamic Finance) инициализирована.")

async def get_current_distribution():
    """Получает текущие коэффициенты распределения из БД."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM distribution_settings WHERE label = 'default'")
        if row:
            return {
                "holders": row['holders_pct'],
                "staking": row['staking_pct'],
                "liquidity": row['liquidity_pct'],
                "treasury": row['treasury_pct']
            }
        return {"holders": 0.02, "staking": 0.30, "liquidity": 0.38, "treasury": 0.30}

async def log_profit_split(total_profit):
    """Логирует профит, используя динамические проценты из таблицы настроек."""
    settings = await get_current_distribution()
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute('''
                INSERT INTO profit_distribution 
                (total_amount, holders_share, staking_share, liquidity_share, treasury_share)
                VALUES ($1, $2, $3, $4, $5)
            ''', 
            total_profit,
            total_profit * settings['holders'],
            total_profit * settings['staking'],
            total_profit * settings['liquidity'],
            total_profit * settings['treasury']
            )
        except Exception as e:
            print(f"🚨 [FINANCE_ERROR]: {e}")

async def get_market_state():
    """Сбор контекста для ИИ из истории операций."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        history = await conn.fetch('''
            SELECT cmd, amount, reason, timestamp 
            FROM neural_mm_logs 
            ORDER BY timestamp DESC LIMIT 15
        ''')
        
        bot_memory = [
            {
                "action": h['cmd'],
                "amt": h['amount'],
                "reason": h['reason'],
                "time": h['timestamp'].strftime('%H:%M:%S')
            } for h in history
        ]

        return {
            "current_metrics": {
                "price_ton": 0.2854,
                "liquidity_ton": 15400.50,
                "volatility_index": 0.045,
                "market_sentiment": "BULLISH_AGGRESSIVE"
            },
            "recent_memory": bot_memory,
            "system_integrity": "OPTIMAL"
        }

async def log_ai_action(plan, market_snapshot=None):
    """Запись действия и автоматическая очистка (Dead Hand Protocol)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                '''INSERT INTO neural_mm_logs (cmd, amount, urgency, reason, market_snapshot) 
                   VALUES ($1, $2, $3, $4, $5)''', 
                plan.get('cmd', 'WAIT'), 
                float(plan.get('amt', 0)), 
                int(plan.get('urgency', 1)), 
                plan.get('reason', 'Neural Pulse Core Execution'),
                json.dumps(market_snapshot) if market_snapshot else None
            )
            
            # Удаляем логи старше 7 дней для экономии места на сервере
            if os.getenv('DB_AUTO_OPTIMIZE', 'true').lower() == 'true':
                await conn.execute("DELETE FROM neural_mm_logs WHERE timestamp < $1", 
                                 datetime.now() - timedelta(days=7))
        except Exception as e:
            print(f"🚨 [DB_ERROR]: {e}")

async def get_stats_for_web():
    """Генерация JSON для фронтенда с учетом новых настроек."""
    pool = await get_pool()
    settings = await get_current_distribution()
    async with pool.acquire() as conn:
        try:
            total_vol = await conn.fetchval("SELECT SUM(amount) FROM neural_mm_logs")
            total_profit = await conn.fetchval("SELECT SUM(total_amount) FROM profit_distribution")
            
            last = await conn.fetchrow('''
                SELECT cmd, reason, timestamp FROM neural_mm_logs 
                ORDER BY timestamp DESC LIMIT 1
            ''')
            
            distribution = await conn.fetch('''
                SELECT cmd, COUNT(*) as count FROM neural_mm_logs GROUP BY cmd
            ''')

            return {
                "summary": {
                    "total_ton_traded": round(total_vol or 0, 2),
                    "total_profit_shared": round(total_profit or 0, 4),
                    "ai_status": "NEURAL_LINK_ACTIVE"
                },
                "telemetry": {
                    "last_cmd": last['cmd'] if last else "IDLE",
                    "last_timestamp": last['timestamp'].strftime('%H:%M:%S') if last else "--:--:--"
                },
                "current_settings": {
                    "holders": f"{settings['holders']*100}%",
                    "staking": f"{settings['staking']*100}%",
                    "liquidity": f"{settings['liquidity']*100}%",
                    "treasury": f"{settings['treasury']*100}%"
                },
                "charts": {
                    "distribution": {row['cmd']: row['count'] for row in distribution}
                }
            }
        except Exception as e:
            print(f"📊 [STATS_ERROR]: {e}")
            return {"status": "error"}
