import asyncio
import os
import json
import time
import sys
import random
import numpy as np
import traceback
import aiosqlite
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# FastAPI компоненты
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- СИСТЕМА ЛОГИРОВАНИЯ ---
LOG_FILE = "quantum_system.log"
DB_PATH = "quantum_vault.db"

def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {
        "INFO": "\033[94m", "SUCCESS": "\033[92m", 
        "WARNING": "\033[93m", "ERROR": "\033[91m", 
        "CORE": "\033[95m", "TRACE": "\033[90m"
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    log_msg = f"[{timestamp}] [{level}] {message}"
    print(f"{color}{log_msg}{reset}", flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")
    except: pass

# --- МОДУЛЬ БАЗЫ ДАННЫХ (DATABASE LOGIC) ---

async def init_db():
    """Инициализация таблиц базы данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS ai_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                address TEXT,
                amount REAL,
                qc_equivalent REAL,
                action_type TEXT,
                status TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS system_config (
                id INTEGER PRIMARY KEY,
                mnemonic TEXT,
                ai_api_key TEXT,
                ai_strategy_level INTEGER DEFAULT 10,
                token_pool_address TEXT,
                referral_commission REAL DEFAULT 15.0,
                yield_percentage REAL DEFAULT 75.0,
                gas_limit_min REAL DEFAULT 0.2
            )
        ''')
        cursor = await db.execute('SELECT id FROM system_config WHERE id = 1')
        if not await cursor.fetchone():
            await db.execute('INSERT INTO system_config (id, ai_strategy_level) VALUES (1, 10)')
        await db.commit()

async def log_ai_action(address, amount, action_type="TRANSACTION", status="SUCCESS"):
    async with aiosqlite.connect(DB_PATH) as db:
        qc_val = float(amount) * 150.0 
        await db.execute('''
            INSERT INTO ai_logs (timestamp, address, amount, qc_equivalent, action_type, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), address, amount, qc_val, action_type, status))
        await db.commit()

async def get_stats_for_web():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM ai_logs ORDER BY id DESC LIMIT 10')
        rows = await cursor.fetchall()
        actions = []
        total_profit = 0.0
        for row in rows:
            actions.append({
                "address": row['address'], "amount": row['amount'],
                "qc": row['qc_equivalent'], "type": row['action_type'],
                "status": row['status'], "time": row['timestamp']
            })
            total_profit += row['amount']
        return {"recent_actions": actions, "total_profit": total_profit}

async def load_remote_config():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM system_config WHERE id = 1')
        row = await cursor.fetchone()
        return dict(row) if row else {}

async def update_remote_config(data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        fields, values = [], []
        keys = ['mnemonic', 'ai_api_key', 'ai_strategy_level', 'token_pool_address', 
                'referral_commission', 'yield_percentage', 'gas_limit_min']
        for key in keys:
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])
        if not fields: return False
        values.append(1)
        query = f"UPDATE system_config SET {', '.join(fields)} WHERE id = ?"
        try:
            await db.execute(query, values)
            await db.commit()
            return True
        except Exception as e:
            log(f"DB Update Error: {e}", "ERROR")
            return False

# --- ИНИЦИАЛИЗАЦИЯ TON ЯДРА ---
log(">>> ЗАПУСК ГИБРИДНОГО ЯДРА QUANTUM V4.1 <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    log("L1: Библиотеки TON (pytoniq) загружены", "SUCCESS")
    TON_ENABLED = True
except ImportError:
    log("Ошибка: pytoniq не найден!", "ERROR")
    TON_ENABLED = False

load_dotenv()

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        self.admin_login = os.getenv("ADMIN_LOGIN", "1")
        self.admin_pass = os.getenv("ADMIN_PASS", "1")
        self.session_token = os.urandom(32).hex() 
        self.pool_addr = None
        self.mnemonic = None
        self.last_status = "INITIALIZING"
        self.current_balance = 0.0

    def get_static_path(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, 'static')
        return path if os.path.exists(path) else "static"

    async def update_config_from_db(self):
        try:
            cfg = await load_remote_config()
            if cfg:
                if cfg.get('mnemonic'):
                    self.mnemonic = cfg['mnemonic'].strip()
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                return True
            return False
        except: return False

overlord = OmniNeuralOverlord()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    worker_task = asyncio.create_task(core_worker())
    yield
    overlord.is_active = False
    worker_task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- ROUTES ---
@app.get("/")
@app.get("/index.html")
async def serve_index():
    return FileResponse(os.path.join(overlord.get_static_path(), "index.html"))

@app.get("/api/stats")
async def get_stats():
    db_stats = await get_stats_for_web()
    current_cfg = await load_remote_config()
    return {
        'balance': f"{db_stats.get('total_profit', 0):.2f}",
        'traffic': round(random.uniform(400, 800), 2),
        'cpu': random.randint(18, 32),
        'connections': random.randint(800, 1200),
        'recent_actions': db_stats.get('recent_actions', []),
        'config': {
            'referral_commission': current_cfg.get('referral_commission', 15),
            'yield_percentage': current_cfg.get('yield_percentage', 75)
        },
        'engine': {"core_id": overlord.core_id, "status": overlord.last_status}
    }

@app.post("/api/update_config")
async def handle_update_config(request: Request):
    data = await request.json()
    if await update_remote_config(data):
        await overlord.update_config_from_db()
        return {"status": "success"}
    return JSONResponse({"status": "error"}, status_code=500)

app.mount("/static", StaticFiles(directory=overlord.get_static_path()), name="static")

async def core_worker():
    while overlord.is_active:
        try:
            await overlord.update_config_from_db()
            if not overlord.mnemonic or not TON_ENABLED:
                overlord.last_status = "WAITING_CONFIG"
                await asyncio.sleep(10); continue
            
            async with LiteClient.from_mainnet_config() as client:
                wallet = await WalletV4R2.from_mnemonic(client, overlord.mnemonic.split())
                overlord.last_status = "ACTIVE"
                while overlord.is_active:
                    overlord.current_balance = (await wallet.get_balance()) / 1e9
                    await asyncio.sleep(30)
        except Exception as e:
            overlord.last_status = "ERROR"
            await asyncio.sleep(10)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 3000)))
