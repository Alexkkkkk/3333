import asyncpg
import os
import json
import asyncio
import random
import hashlib
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import WebSocket

# --- ГЛОБАЛЬНЫЙ ПУЛ СОЕДИНЕНИЙ ---
_pool = None

async def get_pool():
    """Создает пул соединений с лимитами под High-Load."""
    global _pool
    db_url = os.getenv('DATABASE_URL')
    if _pool is None:
        if not db_url:
            raise ValueError("🚨 DATABASE_URL is not set!")
        
        _pool = await asyncpg.create_pool(
            db_url,
            min_size=10, 
            max_size=30,
            command_timeout=60,
            max_queries=100000,
            max_inactive_connection_lifetime=300.0
        )
    return _pool

# --- МЕНЕДЖЕР REAL-TIME СОЕДИНЕНИЙ ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Безопасная рассылка данных всем активным клиентам."""
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

# --- ИНИЦИАЛИЗАЦИЯ КВАНТОВОЙ АРХИТЕКТУРЫ ---
async def init_db():
    """Полная инициализация всех 6 таблиц и индексов."""
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
        
    print("🌌 [DATABASE] Nexus Singularity Core Synchronized.")

# --- УПРАВЛЕНИЕ КОНФИГУРАЦИЕЙ ---
async def load_remote_config():
    pool = await get_pool()
    val = await pool.fetchval("SELECT val FROM quantum_genome WHERE key = 'active_core'")
    if val:
        return json.loads(val) if isinstance(val, str) else val
    return {}

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

async def save_wallet_state(address: str, balance: float, qc: float, network: str = 'MAINNET'):
    pool = await get_pool()
    await pool.execute('''
        INSERT INTO quantum_wallets (address, balance_ton, equity_qc, network, last_seen)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (address) DO UPDATE SET 
            balance_ton = EXCLUDED.balance_ton, 
            equity_qc = EXCLUDED.equity_qc, 
            last_seen = NOW()
    ''', address, float(balance or 0.0), float(qc or 0.0), network)

async def sync_wallet_data(data: dict):
    address = data.get('address')
    if address:
        await save_wallet_state(address, data.get('balance', 0.0), data.get('qc', 0.0))
        return True
    return False

# --- АНАЛИТИКА И ROI ---
async def calculate_roi_stats():
    pool = await get_pool()
    try:
        total = await pool.fetchval('SELECT SUM(equity_qc) FROM quantum_wallets') or 1.0
        p24 = await pool.fetchval("SELECT SUM(total_amount) FROM profit_distribution WHERE timestamp > NOW() - INTERVAL '24 hours'") or 0.0
        return round((float(p24) / float(total)) * 100, 2)
    except Exception:
        return 0.0

async def add_profit_record(amount: float):
    pool = await get_pool()
    amt = float(amount)
    await pool.execute('''
        INSERT INTO profit_distribution (total_amount, holders_share, staking_share, liquidity_share, treasury_share)
        VALUES ($1, $2, $3, $4, $5)
    ''', amt, amt*0.02, amt*0.30, amt*0.38, amt*0.30)

# --- AI ЛОГИРОВАНИЕ ---
async def log_ai_action(cmd, amount=0.0, reason="System Action", market=None):
    pool = await get_pool()
    if isinstance(cmd, dict):
        strategy = cmd
        cmd_text = str(strategy.get('cmd', 'UNKNOWN'))
        amt = float(strategy.get('amount', 0))
        urgency = int(strategy.get('urgency', 1))
        reason_text = str(strategy.get('reason', ''))
    else:
        cmd_text = str(cmd)
        amt = float(amount)
        urgency = 1
        reason_text = str(reason)

    await pool.execute('''
        INSERT INTO neural_mm_logs (cmd, amount, urgency, reason, market_snapshot) 
        VALUES ($1, $2, $3, $4, $5)
    ''', cmd_text, amt, urgency, reason_text, json.dumps(market or {}))

# --- ПОЛУЧЕНИЕ СТАТИСТИКИ ДЛЯ WEB ---
async def get_stats_for_web():
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            online = await conn.fetchval("SELECT COUNT(DISTINCT ip_hash) FROM site_visits WHERE timestamp > NOW() - INTERVAL '30 minutes'") or 0
            total_qc = await conn.fetchval("SELECT SUM(equity_qc) FROM quantum_wallets") or 0.0
            total_w = await conn.fetchval("SELECT COUNT(*) FROM quantum_wallets") or 0
            rows = await conn.fetch('''
                SELECT address, balance_ton as amount, equity_qc as qc, status 
                FROM quantum_wallets ORDER BY last_seen DESC LIMIT 10
            ''')

            roi = await calculate_roi_stats()

            return {
                "connections": int(total_w),
                "qc_balance": round(float(total_qc), 2),
                "traffic": int((online or 1) * 8 + random.randint(1, 5)),
                "roi_24h": roi,
                "recent_actions": [dict(r) for r in rows],
                "system": {
                    "cpu": random.randint(18, 32),
                    "ram": f"{random.randint(150, 172)}MB"
                }
            }
    except Exception as e:
        print(f"Stats error: {e}")
        return {"traffic": 0, "connections": 0, "qc_balance": 0, "roi_24h": 0, "recent_actions": []}

# --- КВАНТОВЫЙ ОРКЕСТРАТОР ---
class QuantumOrchestrator:
    @staticmethod
    async def pulse():
        """Периодическая рассылка статистики всем клиентам по WS."""
        while True:
            try:
                stats = await get_stats_for_web()
                await manager.broadcast({"type": "UPDATE", "event": "CORE_PULSE", "data": stats})
            except Exception:
                pass
            await asyncio.sleep(5)

    @staticmethod
    async def cleanup():
        """Автоматическая очистка старых записей каждые 12 часов."""
        while True:
            await asyncio.sleep(43200) 
            try:
                pool = await get_pool()
                await pool.execute("DELETE FROM site_visits WHERE timestamp < NOW() - INTERVAL '24 hours'")
                await pool.execute("DELETE FROM neural_mm_logs WHERE timestamp < NOW() - INTERVAL '7 days'")
                print("🧹 [DATABASE] Cleanup completed.")
            except Exception as e:
                print(f"Cleanup error: {e}")
