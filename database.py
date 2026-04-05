import asyncpg
import os
import json
import asyncio
from datetime import datetime, timedelta

# Глобальный пул соединений для эффективной работы на Bothost
_pool = None

async def get_pool():
    """Создает пул соединений с High-Load лимитами."""
    global _pool
    db_url = os.getenv('DATABASE_URL')
    if _pool is None:
        if not db_url:
            raise ValueError("🚨 DATABASE_URL is not set in environment variables!")
        
        _pool = await asyncpg.create_pool(
            db_url,
            min_size=10,
            max_size=50,
            command_timeout=60,
            max_queries=100000,
            max_inactive_connection_lifetime=300.0
        )
    return _pool

async def init_db():
    """Инициализация всей архитектуры БД: Конфиг, Логи, Профит."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 0. ТАБЛИЦА ГЛОБАЛЬНОЙ КОНФИГУРАЦИИ
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_config (
                id SERIAL PRIMARY KEY,
                mnemonic TEXT,
                ai_api_key TEXT,
                ai_strategy_level INTEGER DEFAULT 10,
                target_jetton TEXT,
                dedust_pool TEXT,
                delta_sync_ms INTEGER DEFAULT 500,
                is_active BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 1. ТАБЛИЦА НАСТРОЕК РАСПРЕДЕЛЕНИЯ ПРОФИТА
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

        # 2. ТАБЛИЦА НЕЙРО-ЛОГОВ (Хранение истории действий ИИ)
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
        
        # 3. ТАБЛИЦА РАСПРЕДЕЛЕНИЯ ПРИБЫЛИ
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
        
        # Оптимизация: Индексы для ускорения работы Admin Panel
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp_desc ON neural_mm_logs(timestamp DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_config_active ON bot_config(is_active)')
        
        print("✅ [DATABASE] Neural Pulse V28 Architecture Synchronized.")

# --- ФУНКЦИИ УПРАВЛЕНИЯ КОНФИГУРАЦИЕЙ ---

async def load_remote_config():
    """Загрузка настроек для работы торгового ядра."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('''
            SELECT mnemonic, ai_api_key, ai_strategy_level, target_jetton, dedust_pool, delta_sync_ms 
            FROM bot_config 
            WHERE is_active = TRUE 
            ORDER BY updated_at DESC LIMIT 1
        ''')
        return dict(row) if row else None

async def update_remote_config(data: dict):
    """Обновление настроек через Admin Panel."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO bot_config (
                mnemonic, ai_api_key, target_jetton, dedust_pool, ai_strategy_level, is_active
            )
            VALUES ($1, $2, $3, $4, $5, TRUE)
        ''', 
        data.get('mnemonic'), 
        data.get('ai_api_key'), 
        data.get('target_jetton'), 
        data.get('dedust_pool'), 
        int(data.get('ai_strategy_level', 10))
        )
        return True

# --- АНАЛИТИКА И ЛОГИРОВАНИЕ ---

async def get_current_distribution():
    """Получение текущих коэффициентов прибыли."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT holders_pct, staking_pct, liquidity_pct, treasury_pct FROM distribution_settings WHERE label = 'default'")
        return dict(row) if row else {"holders_pct": 0.02, "staking_pct": 0.30, "liquidity_pct": 0.38, "treasury_pct": 0.30}

async def get_market_state():
    """Анализ тренда на основе истории логов."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        history = await conn.fetch('''
            SELECT cmd, amount, reason, market_snapshot, timestamp 
            FROM neural_mm_logs 
            ORDER BY timestamp DESC LIMIT 30
        ''')
        
        prices = []
        for h in history:
            ms = h['market_snapshot']
            if ms:
                # Безопасная распаковка JSONB
                val = ms.get('price_ton', 0) if isinstance(ms, dict) else json.loads(ms).get('price_ton', 0)
                prices.append(float(val))
        
        trend = "STABLE"
        current_price = 0.0
        
        if prices:
            current_price = prices[0]
            if len(prices) > 1:
                delta = prices[0] - prices[-1]
                if abs(delta) > 0.0001:
                    trend = "UPWARD" if delta > 0 else "DOWNWARD"

        bot_memory = [
            {
                "action": h['cmd'], 
                "amt": h['amount'], 
                "reason": h.get('reason', 'N/A'), 
                "time": h['timestamp'].strftime('%H:%M:%S') if h['timestamp'] else "00:00:00"
            } 
            for h in history[:15]
        ]

        return {
            "current_metrics": {
                "price_ton": current_price,
                "liquidity_ton": 15400.50, 
                "market_trend": trend,
                "sentiment": "NEURAL_ANALYZED"
            },
            "recent_memory": bot_memory
        }

async def log_ai_action(strategy, market, perf_data=None):
    """Запись действий ИИ и автоматическая очистка старых записей."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            cmd = strategy.get('cmd', 'WAIT')
            amount = float(strategy.get('amt', 0.0))
            urgency = int(strategy.get('urgency', 1))
            reason = strategy.get('reason', 'Routine analysis')
            
            await conn.execute('''
                INSERT INTO neural_mm_logs (cmd, amount, urgency, reason, market_snapshot, performance_metrics) 
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', cmd, amount, urgency, reason, json.dumps(market), json.dumps(perf_data) if perf_data else None)
            
            # Очистка базы: удаляем логи старше 7 дней, чтобы не забивать диск
            await conn.execute("DELETE FROM neural_mm_logs WHERE timestamp < NOW() - INTERVAL '7 days'")
        except Exception as e:
            print(f"🚨 [DB_LOG_ERROR]: {e}")

async def add_profit_record(amount):
    """Фиксация прибыли и её автоматическое распределение."""
    pool = await get_pool()
    s = await get_current_distribution()
    amount = float(amount)
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO profit_distribution 
            (total_amount, holders_share, staking_share, liquidity_share, treasury_share)
            VALUES ($1, $2, $3, $4, $5)
        ''', amount, amount*s['holders_pct'], amount*s['staking_pct'], amount*s['liquidity_pct'], amount*s['treasury_pct'])
        print(f"💰 [PROFIT] {amount} TON shared by neural algorithm.")

async def get_stats_for_web():
    """Сбор статистики для графиков в админ-панели."""
    pool = await get_pool()
    dist_settings = await get_current_distribution()
    async with pool.acquire() as conn:
        total_vol = await conn.fetchval("SELECT SUM(amount) FROM neural_mm_logs") or 0
        total_profit = await conn.fetchval("SELECT SUM(total_amount) FROM profit_distribution") or 0
        
        # Распределение типов команд для круговой диаграммы
        distribution_rows = await conn.fetch("SELECT cmd, COUNT(*) as count FROM neural_mm_logs GROUP BY cmd")
        cmd_dist = {row['cmd']: row['count'] for row in distribution_rows}

        return {
            "summary": {
                "total_volume": round(float(total_vol), 2),
                "total_profit": round(float(total_profit), 2),
                "status": "SINGULARITY_ACTIVE"
            },
            "distribution": dist_settings,
            "strategy_map": cmd_dist
        }
