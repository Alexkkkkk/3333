import asyncpg
import os
import json
import asyncio
import random
import hashlib
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
    """Инициализация Квантовой Архитектуры БД."""
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
                balance_ton DOUBLE PRECISION DEFAULT 0.0,
                equity_qc DOUBLE PRECISION DEFAULT 0.0,
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
                amount DOUBLE PRECISION DEFAULT 0.0,
                urgency INT DEFAULT 1,
                reason TEXT,
                market_snapshot JSONB,
                reward_score DOUBLE PRECISION DEFAULT 0.0,
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
                total_amount DOUBLE PRECISION NOT NULL,
                holders_share DOUBLE PRECISION,
                staking_share DOUBLE PRECISION,
                liquidity_share DOUBLE PRECISION,
                treasury_share DOUBLE PRECISION,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 6. ТАБЛИЦА ВЫВОДА СРЕДСТВ
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                id SERIAL PRIMARY KEY,
                address TEXT NOT NULL,
                amount_ton DOUBLE PRECISION NOT NULL,
                status TEXT DEFAULT 'PENDING',
                tx_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        ''')

        # Базовая настройка генома
        default_val = {
            "mnemonic": "",
            "ai_api_key": "",
            "ai_strategy_level": 10,
            "referral_commission": 15.0,
            "yield_percentage": 75.0,
            "gas_limit_min": 0.2
        }
        await conn.execute('''
            INSERT INTO quantum_genome (key, val, is_shadow) 
            VALUES ('active_core', $1, FALSE)
            ON CONFLICT DO NOTHING
        ''', json.dumps(default_val))

        # Индексы для оптимизации
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_neural_ts ON neural_mm_logs(timestamp DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_wallets_qc ON quantum_wallets(equity_qc DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_profit_ts ON profit_distribution(timestamp DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_withdraw_status ON withdrawal_requests(status)')
        
        print("🌌 [DATABASE] Nexus Singularity Core Synchronized.")

# --- УПРАВЛЕНИЕ КОНФИГУРАЦИЕЙ ---

async def load_remote_config():
    pool = await get_pool()
    val = await pool.fetchval("SELECT val FROM quantum_genome WHERE key = 'active_core'")
    return json.loads(val) if val else {}

async def update_remote_config(data: dict):
    pool = await get_pool()
    current = await load_remote_config()
    current.update(data)
    await pool.execute('''
        INSERT INTO quantum_genome (key, val) 
        VALUES ('active_core', $1) 
        ON CONFLICT (key) DO UPDATE SET val = $1, updated_at = NOW()
    ''', json.dumps(current))
    return True

# --- УЧЕТ ПОСЕТИТЕЛЕЙ И КОШЕЛЬКОВ ---

async def register_visit(ip: str, user_agent: str):
    pool = await get_pool()
    await pool.execute('INSERT INTO site_visits (ip_hash, user_agent) VALUES (MD5($1), $2)', ip, user_agent)
    # Авто-очистка старых визитов (храним только за последние 24 часа)
    await pool.execute("DELETE FROM site_visits WHERE timestamp < NOW() - INTERVAL '24 hours'")

async def save_wallet_state(address: str, balance: float, qc: float, network: str = 'MAINNET'):
    pool = await get_pool()
    await pool.execute('''
        INSERT INTO quantum_wallets (address, balance_ton, equity_qc, network, last_seen)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (address) DO UPDATE SET 
            balance_ton = EXCLUDED.balance_ton, 
            equity_qc = EXCLUDED.equity_qc, 
            last_seen = NOW(),
            status = 'ACTIVE'
    ''', address, float(balance), float(qc), network)

async def get_user_balance(address: str):
    pool = await get_pool()
    res = await pool.fetchval('SELECT balance_ton FROM quantum_wallets WHERE address = $1', address)
    return float(res) if res else 0.0

# --- СИСТЕМА ВЫВОДА ---

async def create_withdrawal_request(address: str, amount: float):
    pool = await get_pool()
    active = await pool.fetchval("SELECT id FROM withdrawal_requests WHERE address = $1 AND status = 'PENDING'", address)
    if active:
        return False, "У вас уже есть активная заявка"
    
    await pool.execute('''
        INSERT INTO withdrawal_requests (address, amount_ton) VALUES ($1, $2)
    ''', address, float(amount))
    return True, "Заявка создана"

async def update_withdrawal_status(request_id: int, status: str, tx_hash: str = None):
    pool = await get_pool()
    result = await pool.execute('''
        UPDATE withdrawal_requests 
        SET status = $2, tx_hash = $3, processed_at = NOW() 
        WHERE id = $1
    ''', request_id, status, tx_hash)
    return result == "UPDATE 1"

# --- АНАЛИТИКА ---

async def calculate_roi_stats():
    pool = await get_pool()
    total_assets = await pool.fetchval('SELECT SUM(equity_qc) FROM quantum_wallets') or 1.0
    profit_24h = await pool.fetchval('''
        SELECT SUM(total_amount) FROM profit_distribution 
        WHERE timestamp > NOW() - INTERVAL '24 hours'
    ''') or 0.0
    return round((float(profit_24h) / float(total_assets)) * 100, 2)

async def add_profit_record(amount):
    pool = await get_pool()
    amt = float(amount)
    await pool.execute('''
        INSERT INTO profit_distribution 
        (total_amount, holders_share, staking_share, liquidity_share, treasury_share)
        VALUES ($1, $2, $3, $4, $5)
    ''', amt, amt*0.02, amt*0.30, amt*0.38, amt*0.30)

# --- AI LOGS ---

async def log_ai_action(strategy, market, success_metric=0.0):
    pool = await get_pool()
    await pool.execute('''
        INSERT INTO neural_mm_logs (cmd, amount, urgency, reason, market_snapshot, reward_score) 
        VALUES ($1, $2, $3, $4, $5, $6)
    ''', strategy.get('cmd'), float(strategy.get('amount', 0)), 
         int(strategy.get('urgency', 1)), strategy.get('reason'), 
         json.dumps(market), float(success_metric))
    # Самоочистка: удаляем логи старше 7 дней
    await pool.execute("DELETE FROM neural_mm_logs WHERE timestamp < NOW() - INTERVAL '7 days'")

# --- ВЕБ-СТАТИСТИКА ---

async def get_stats_for_web():
    pool = await get_pool()
    # Берем данные об активности за последние 30 минут для плавности трафика
    active_users = await pool.fetchval('''
        SELECT COUNT(DISTINCT ip_hash) FROM site_visits 
        WHERE timestamp > NOW() - INTERVAL '30 minutes'
    ''') or 0

    rows = await pool.fetch('''
        SELECT address, balance_ton as amount, equity_qc as qc, status 
        FROM quantum_wallets ORDER BY last_seen DESC LIMIT 10
    ''')

    total_qc = await pool.fetchval('SELECT SUM(equity_qc) FROM quantum_wallets') or 0.0
    total_wallets = await pool.fetchval('SELECT COUNT(*) FROM quantum_wallets') or 0
    roi = await calculate_roi_stats()

    return {
        "connections": total_wallets,
        "qc_balance": float(total_qc),        # Поле для отображения общего баланса QC
        "balance": 0.0,                       # Заглушка под общий баланс TON (если потребуется)
        "traffic": int((active_users or 1) * 6), # Множитель для красивой статистики трафика
        "roi_24h": roi,
        "recent_actions": [dict(r) for r in rows],
        "cpu": random.randint(15, 30)         # Эмуляция загрузки процессора в реальном времени
    }
