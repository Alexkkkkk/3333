import asyncpg
import os
import json
import asyncio
import random
from datetime import datetime, timedelta

# Глобальный пул соединений
_pool = None

async def get_pool():
    """Создает пул соединений с High-Load лимитами для Bothost."""
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
    """Инициализация Квантовой Архитектуры БД: Сингулярность и Теневые реальности."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 1. ТАБЛИЦА ГЕНОМА (Активные и Теневые параметры)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS quantum_genome (
                key TEXT PRIMARY KEY,
                val JSONB,
                is_shadow BOOLEAN DEFAULT FALSE,
                fitness_score FLOAT DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 2. ТАБЛИЦА НЕЙРО-ЛОГОВ (Опыт системы)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS neural_mm_logs (
                id SERIAL PRIMARY KEY,
                cmd TEXT NOT NULL,
                amount FLOAT DEFAULT 0.0,
                urgency INT DEFAULT 1,
                reason TEXT,
                market_snapshot JSONB,
                reward_score FLOAT DEFAULT 0.0, -- Оценка успеха действия
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

        # Инициализация базового генома, если пусто
        await conn.execute('''
            INSERT INTO quantum_genome (key, val, is_shadow) 
            VALUES ('trade_logic', '{"risk": 0.1, "agression": 0.5, "min_liq": 1000}', FALSE)
            ON CONFLICT DO NOTHING
        ''')

        # Индексы для мгновенной аналитики
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_neural_ts ON neural_mm_logs(timestamp DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_reward ON neural_mm_logs(reward_score)')
        
        print("🌌 [DATABASE] Nexus Singularity Core Synchronized.")

# --- СИСТЕМА САМООБУЧЕНИЯ (REINFORCEMENT LEARNING) ---

async def log_ai_action(strategy, market, success_metric=0.0):
    """Запись действия с оценкой вознаграждения (Reward)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Расчет Reward: успех + объем - (латентность/1000)
        reward = success_metric if strategy.get('cmd') != 'WAIT' else 0.01
        
        await conn.execute('''
            INSERT INTO neural_mm_logs (cmd, amount, urgency, reason, market_snapshot, reward_score) 
            VALUES ($1, $2, $3, $4, $5, $6)
        ''', strategy.get('cmd'), float(strategy.get('amt', 0)), 
             int(strategy.get('urgency', 1)), strategy.get('reason'), 
             json.dumps(market), float(reward))
        
        # Авто-очистка: храним опыт за 7 дней
        await conn.execute("DELETE FROM neural_mm_logs WHERE timestamp < NOW() - INTERVAL '7 days'")

async def evolve_system():
    """
    Генетический алгоритм: создает 'теневую' версию конфига, 
    мутирует её и проверяет, лучше ли она текущей.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Получаем средний профит текущей системы
        current_perf = await conn.fetchval('''
            SELECT AVG(reward_score) FROM neural_mm_logs 
            WHERE timestamp > NOW() - INTERVAL '1 hour'
        ''') or 0.0

        # Получаем активный конфиг
        active = await conn.fetchrow("SELECT val FROM quantum_genome WHERE is_shadow = FALSE LIMIT 1")
        if not active: return

        genome = json.loads(active['val'])
        
        # МУТАЦИЯ: Создаем теневой конфиг с небольшим отклонением (Entropy)
        shadow_genome = genome.copy()
        for k in shadow_genome:
            if isinstance(shadow_genome[k], (int, float)):
                shadow_genome[k] *= random.uniform(0.9, 1.1)

        # Сохраняем в тень
        await conn.execute('''
            INSERT INTO quantum_genome (key, val, is_shadow, fitness_score) 
            VALUES ('trade_logic_shadow', $1, TRUE, 0.0)
            ON CONFLICT (key) DO UPDATE SET val = EXCLUDED.val
        ''', json.dumps(shadow_genome))

        # Если текущий перформанс падает ниже порога, а тень показала бы себя лучше 
        # (здесь упрощенная логика Reality Swap)
        if current_perf < -0.5:
            print("💫 [DATABASE] Reality Collapse! Swapping to Shadow Genome.")
            await conn.execute("UPDATE quantum_genome SET val = (SELECT val FROM quantum_genome WHERE is_shadow = TRUE) WHERE is_shadow = FALSE")

# --- УПРАВЛЕНИЕ КОНФИГУРАЦИЕЙ И РАСПРЕДЕЛЕНИЕМ ---

async def load_nexus_config():
    """Загрузка активного генома системы."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT val FROM quantum_genome WHERE is_shadow = FALSE ORDER BY updated_at DESC LIMIT 1")
        return json.loads(row['val']) if row else {}

async def add_profit_record(amount):
    """Фиксация прибыли с автоматическим расчетом долей (Nexus Distribution)."""
    pool = await get_pool()
    # Коэффициенты по умолчанию
    shares = {"holders": 0.02, "staking": 0.30, "liquidity": 0.38, "treasury": 0.30}
    
    amount = float(amount)
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO profit_distribution 
            (total_amount, holders_share, staking_share, liquidity_share, treasury_share)
            VALUES ($1, $2, $3, $4, $5)
        ''', amount, amount*shares['holders'], amount*shares['staking'], 
             amount*shares['liquidity'], amount*shares['treasury'])
        
        # Обучаем систему: профит — это высокая награда
        await log_ai_action({'cmd': 'PROFIT_TAKE', 'amt': amount, 'reason': 'System Gain'}, {}, success_metric=1.0)

async def get_market_state():
    """Предиктивный анализ тренда на основе истории вознаграждений."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        history = await conn.fetch('''
            SELECT cmd, amount, reward_score, timestamp 
            FROM neural_mm_logs 
            ORDER BY timestamp DESC LIMIT 20
        ''')
        
        # Анализ тренда успеха
        rewards = [h['reward_score'] for h in history]
        avg_reward = sum(rewards) / len(rewards) if rewards else 0
        
        trend = "STABLE"
        if len(rewards) > 5:
            delta = rewards[0] - rewards[-1]
            trend = "OPTIMIZING" if delta > 0 else "DEGRADATION"

        return {
            "status": "OPERATIONAL",
            "neural_health": round(avg_reward, 4),
            "trend": trend,
            "memory_depth": len(history)
        }

async def get_web_analytics():
    """Сбор данных для Dashboards (Singularity Visualizer)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        stats = await conn.fetchrow('''
            SELECT 
                SUM(total_amount) as total_profit,
                COUNT(*) as distribution_events
            FROM profit_distribution
        ''')
        
        cmd_stats = await conn.fetch("SELECT cmd, COUNT(*) as count FROM neural_mm_logs GROUP BY cmd")
        
        return {
            "total_profit": float(stats['total_profit'] or 0),
            "events": stats['distribution_events'],
            "strategy_distribution": {r['cmd']: r['count'] for r in cmd_stats}
        }
