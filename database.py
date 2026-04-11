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
            min_size=5,
            max_size=20,
            command_timeout=60,
            max_queries=100000,
            max_inactive_connection_lifetime=300.0
        )
    return _pool

async def init_db():
    """Инициализация Квантовой Архитектуры БД: Сингулярность, Узлы и Трафик."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 1. ТАБЛИЦА ГЕНОМА (Конфигурации)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS quantum_genome (
                key TEXT PRIMARY KEY,
                val JSONB,
                is_shadow BOOLEAN DEFAULT FALSE,
                fitness_score FLOAT DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 2. ТАБЛИЦА КОШЕЛЬКОВ (Узлы системы)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS quantum_wallets (
                address TEXT PRIMARY KEY,
                balance_ton FLOAT DEFAULT 0.0,
                equity_qc FLOAT DEFAULT 0.0,
                network TEXT DEFAULT 'MAINNET',
                status TEXT DEFAULT 'ACTIVE',
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 3. ТАБЛИЦА НЕЙРО-ЛОГОВ (Опыт системы)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS neural_mm_logs (
                id SERIAL PRIMARY KEY,
                cmd TEXT NOT NULL,
                amount FLOAT DEFAULT 0.0,
                urgency INT DEFAULT 1,
                reason TEXT,
                market_snapshot JSONB,
                reward_score FLOAT DEFAULT 0.0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 4. ТАБЛИЦА ПОСЕЩЕНИЙ (Аналитика трафика)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS site_visits (
                id SERIAL PRIMARY KEY,
                ip_hash TEXT,
                user_agent TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 5. ТАБЛИЦА РАСПРЕДЕЛЕНИЯ ПРИБЫЛИ
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

        # Базовая настройка генома
        await conn.execute('''
            INSERT INTO quantum_genome (key, val, is_shadow) 
            VALUES ('active_core', '{"risk": 0.1, "agression": 0.5, "min_liq": 1000, "mnemonic": ""}', FALSE)
            ON CONFLICT DO NOTHING
        ''')

        # Индексы для оптимизации
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_neural_ts ON neural_mm_logs(timestamp DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_wallets_qc ON quantum_wallets(equity_qc DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_profit_ts ON profit_distribution(timestamp DESC)')
        
        print("🌌 [DATABASE] Nexus Singularity Core Synchronized. Analytics Module Active.")

# --- СИСТЕМА УЧЕТА ПОЛЬЗОВАТЕЛЕЙ И КОШЕЛЬКОВ ---

async def register_visit(ip: str, user_agent: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('INSERT INTO site_visits (ip_hash, user_agent) VALUES (MD5($1), $2)', ip, user_agent)

async def save_wallet_state(address: str, balance: float, qc: float, network: str = 'MAINNET'):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO quantum_wallets (address, balance_ton, equity_qc, network, last_seen)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (address) DO UPDATE SET 
                balance_ton = EXCLUDED.balance_ton, 
                equity_qc = EXCLUDED.equity_qc, 
                last_seen = NOW(),
                status = 'SUCCESS'
        ''', address, float(balance), float(qc), network)

# --- АНАЛИТИКА ДОХОДНОСТИ ---

async def calculate_roi_stats():
    """Расчет процента прибыли за 24 часа относительно общей капитализации."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Общая масса QC в системе
        total_assets = await conn.fetchval('SELECT SUM(equity_qc) FROM quantum_wallets') or 1.0
        # Прибыль за последние 24 часа
        profit_24h = await conn.fetchval('''
            SELECT SUM(total_amount) FROM profit_distribution 
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        ''') or 0.0
        
        roi_percent = (profit_24h / total_assets) * 100
        return round(roi_percent, 2)

# --- СИСТЕМА САМООБУЧЕНИЯ (REINFORCEMENT LEARNING) ---

async def log_ai_action(strategy, market, success_metric=0.0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        reward = success_metric if strategy.get('cmd') != 'WAIT' else 0.01
        await conn.execute('''
            INSERT INTO neural_mm_logs (cmd, amount, urgency, reason, market_snapshot, reward_score) 
            VALUES ($1, $2, $3, $4, $5, $6)
        ''', strategy.get('cmd'), float(strategy.get('amt', 0)), 
             int(strategy.get('urgency', 1)), strategy.get('reason'), 
             json.dumps(market), float(reward))
        
        await conn.execute("DELETE FROM neural_mm_logs WHERE timestamp < NOW() - INTERVAL '7 days'")

# --- СБОР ДАННЫХ ДЛЯ ВЕБ-ИНТЕРФЕЙСА ---

async def get_stats_for_web():
    """Сбор данных для фронтенда."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 1. Трафик
        active_users = await conn.fetchval('''
            SELECT COUNT(DISTINCT ip_hash) FROM site_visits 
            WHERE timestamp > NOW() - INTERVAL '15 minutes'
        ''') or 0

        # 2. Последние узлы (кошельки)
        wallets_rows = await conn.fetch('''
            SELECT address, balance_ton as amount, equity_qc as qc, network as type, status 
            FROM quantum_wallets ORDER BY last_seen DESC LIMIT 10
        ''')

        # 3. Глобальные метрики
        total_qc = await conn.fetchval('SELECT SUM(equity_qc) FROM quantum_wallets') or 0
        total_wallets = await conn.fetchval('SELECT COUNT(*) FROM quantum_wallets') or 0
        roi_percent = await calculate_roi_stats()

        recent_actions = [dict(row) for row in wallets_rows]
        
        return {
            "connections": total_wallets,
            "balance": float(total_qc),
            "traffic": active_users * 7,
            "profit_percent": roi_percent,     # Процент прибыли для дашборда
            "recent_actions": recent_actions,
            "cpu": random.randint(32, 48)
        }

async def add_profit_record(amount):
    """Фиксация прибыли."""
    pool = await get_pool()
    shares = {"holders": 0.02, "staking": 0.30, "liquidity": 0.38, "treasury": 0.30}
    amount = float(amount)
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO profit_distribution 
            (total_amount, holders_share, staking_share, liquidity_share, treasury_share)
            VALUES ($1, $2, $3, $4, $5)
        ''', amount, amount*shares['holders'], amount*shares['staking'], 
             amount*shares['liquidity'], amount*shares['treasury'])
        
        await log_ai_action({'cmd': 'PROFIT_TAKE', 'amt': amount, 'reason': 'ROI Growth'}, {}, success_metric=1.0)
