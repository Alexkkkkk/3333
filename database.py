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
    """Инициализация архитектуры: Логи, Финансы и Аналитика."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 1. ТАБЛИЦА НАСТРОЕК РАСПРЕДЕЛЕНИЯ
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

        await conn.execute('''
            INSERT INTO distribution_settings (label, holders_pct, staking_pct, liquidity_pct, treasury_pct)
            VALUES ('default', 0.02, 0.30, 0.38, 0.30)
            ON CONFLICT (label) DO NOTHING
        ''')

        # 2. ТАБЛИЦА НЕЙРО-ЛОГОВ (JSONB для глубокой аналитики)
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
        
        # 3. ТАБЛИЦА ПРИБЫЛИ (Бухгалтерия системы)
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
        
        # Индексы для мгновенной выборки (High-Load Optimization)
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp_desc ON neural_mm_logs(timestamp DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_cmd_lookup ON neural_mm_logs(cmd)')
        
        print("✅ [DATABASE] Система Neural Pulse V28 (Ultra Analytics) инициализирована.")

async def get_current_distribution():
    """Получение текущих коэффициентов распределения профита."""
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

async def get_market_state():
    """Сбор контекста для ИИ: извлекает тренды из истории логов."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        history = await conn.fetch('''
            SELECT cmd, amount, reason, market_snapshot, timestamp 
            FROM neural_mm_logs 
            ORDER BY timestamp DESC LIMIT 30
        ''')
        
        prices = [h['market_snapshot'].get('price_ton', 0) for h in history if h['market_snapshot']]
        trend = "STABLE"
        if len(prices) > 1:
            delta = prices[0] - prices[-1]
            trend = "UPWARD" if delta > 0 else "DOWNWARD"

        bot_memory = [
            {
                "action": h['cmd'],
                "amt": h['amount'],
                "reason": h['reason'],
                "time": h['timestamp'].strftime('%H:%M:%S')
            } for h in history[:15]
        ]

        return {
            "current_metrics": {
                "price_ton": prices[0] if prices else 0.2854,
                "liquidity_ton": 15400.50, # В реале подтяни из DeDust API
                "volatility_index": 0.045,
                "market_trend": trend,
                "sentiment": "NEURAL_ANALYZED"
            },
            "recent_memory": bot_memory,
            "integrity": "OPTIMAL"
        }

async def log_ai_action(plan, market_snapshot=None, perf_data=None):
    """Запись действия с расчетом эффективности и авто-очисткой базы."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                '''INSERT INTO neural_mm_logs (cmd, amount, urgency, reason, market_snapshot, performance_metrics) 
                   VALUES ($1, $2, $3, $4, $5, $6)''', 
                plan.get('cmd', 'WAIT'), 
                float(plan.get('amt', 0)), 
                int(plan.get('urgency', 1)), 
                plan.get('reason', 'Core Analysis Execution'),
                json.dumps(market_snapshot) if market_snapshot else None,
                json.dumps(perf_data) if perf_data else None
            )
            
            # Очистка старых данных (7 дней), чтобы база не тормозила
            if os.getenv('DB_AUTO_OPTIMIZE', 'true').lower() == 'true':
                await conn.execute("DELETE FROM neural_mm_logs WHERE timestamp < $1", 
                                 datetime.now() - timedelta(days=7))
        except Exception as e:
            print(f"🚨 [DB_ERROR]: {e}")

async def get_stats_for_web():
    """Генерация JSON с расширенной аналитикой для Web-интерфейса."""
    pool = await get_pool()
    settings = await get_current_distribution()
    async with pool.acquire() as conn:
        try:
            total_vol = await conn.fetchval("SELECT SUM(amount) FROM neural_mm_logs") or 0
            total_profit = await conn.fetchval("SELECT SUM(total_amount) FROM profit_distribution") or 0
            
            day_ago = datetime.now() - timedelta(hours=24)
            daily_profit = await conn.fetchval("SELECT SUM(total_amount) FROM profit_distribution WHERE timestamp > $1", day_ago) or 0
            
            last = await conn.fetchrow('''
                SELECT cmd, reason, timestamp FROM neural_mm_logs 
                ORDER BY timestamp DESC LIMIT 1
            ''')
            
            distribution_rows = await conn.fetch('''
                SELECT cmd, COUNT(*) as count FROM neural_mm_logs GROUP BY cmd
            ''')
            cmd_dist = {row['cmd']: row['count'] for row in distribution_rows}

            return {
                "summary": {
                    "total_ton_traded": round(total_vol, 2),
                    "total_profit_shared": round(total_profit, 2),
                    "daily_profit": round(daily_profit, 2),
                    "status": "ACTIVE_PULSE"
                },
                "last_action": {
                    "cmd": last['cmd'] if last else "INITIALIZING",
                    "reason": last['reason'] if last else "System startup",
                    "time": last['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if last else None
                },
                "distribution": settings,
                "strategy_map": cmd_dist,
                "server_time": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"🚨 [STATS_ERROR]: {e}")
            return {"error": str(e)}

async def add_profit_record(amount):
    """Разделяет прибыль по кошелькам при поступлении."""
    pool = await get_pool()
    s = await get_current_distribution()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO profit_distribution 
            (total_amount, holders_share, staking_share, liquidity_share, treasury_share)
            VALUES ($1, $2, $3, $4, $5)
        ''', amount, amount*s['holders'], amount*s['staking'], amount*s['liquidity'], amount*s['treasury'])
        print(f"💰 [PROFIT] Зачислено {amount} TON. Доли распределены.")
