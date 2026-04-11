import asyncio
import os
import json
import time
import sys
import random
import numpy as np
import traceback
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

# --- ИНИЦИАЛИЗАЦИЯ TON ЯДРА ---
log(">>> ЗАПУСК ГИБРИДНОГО ЯДРА QUANTUM V3.0 (FastAPI + AI) <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address, begin_cell as BeginCell
    log("L1: Библиотеки TON (pytoniq) загружены", "SUCCESS")
    TON_ENABLED = True
except ImportError:
    log("Критическая ошибка: pytoniq не найден!", "ERROR")
    TON_ENABLED = False

try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("L2: Модули базы данных подключены", "SUCCESS")
    DB_ENABLED = True
except ImportError:
    log("L2 ERROR: Файл database.py не найден! Используются заглушки.", "ERROR")
    DB_ENABLED = False
    async def init_db(): pass
    async def log_ai_action(*args): pass
    async def get_market_state(): return {}
    async def get_stats_for_web(): return {}
    async def load_remote_config(): return {}
    async def update_remote_config(*args): pass

load_dotenv()

# --- УПРАВЛЕНИЕ ЯДРОМ ---
class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        self.admin_login = os.getenv("ADMIN_LOGIN", "1")
        self.admin_pass = os.getenv("ADMIN_PASS", "1")
        self.session_token = os.urandom(32).hex() 
        
        self.pool_addr = None
        self.vault_ton = Address("UQBo0iou1BlB_8Xg0Hn_rUeIcrpyyhoboIauvnii889OFRoI")
        self.mnemonic = None
        self.ai_key = None
        self.strategy_level = 10
        
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        self.current_balance = 0.0

    def get_static_path(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        check_paths = [
            os.path.join(base_dir, 'static'),
            os.path.join(os.getcwd(), 'static'),
            '/app/static',
            'static'
        ]
        for p in check_paths:
            if os.path.exists(p) and os.path.isdir(p): 
                return p
        return "static"

    async def update_config_from_db(self):
        try:
            cfg = await load_remote_config()
            if cfg:
                if cfg.get('mnemonic'):
                    self.mnemonic = " ".join(str(cfg.get('mnemonic')).replace('\n', ' ').strip().split())
                self.ai_key = str(cfg.get('ai_api_key', '')).strip()
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                
                pool_raw = str(cfg.get('dedust_pool', cfg.get('token_pool_address', ''))).strip()
                if pool_raw and pool_raw != "None":
                    try: self.pool_addr = Address(pool_raw)
                    except: log(f"Bad Pool Addr: {pool_raw}", "WARNING")
                return True
            return False
        except Exception as e:
            log(f"Config Sync Error: {e}", "ERROR")
            return False

overlord = OmniNeuralOverlord()

@asynccontextmanager
async def lifespan(app: FastAPI):
    log(f">>> ЯДРО {overlord.core_id} ГОТОВО К РАБОТЕ <<<", "CORE")
    worker_task = asyncio.create_task(core_worker())
    yield
    overlord.is_active = False
    worker_task.cancel()
    log(">>> СИСТЕМА ДЕАКТИВИРОВАНА <<<", "CORE")

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# --- WEB ROUTES (Фиксы 404 для Bothost) ---

@app.get("/")
@app.get("/index.html")
async def serve_index():
    path = os.path.join(overlord.get_static_path(), "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({"error": "Index not found"}, status_code=404)

@app.get("/admin")
@app.get("/admin.html")
async def serve_admin():
    static_dir = overlord.get_static_path()
    check_files = [
        os.path.join(static_dir, "admin.html"),
        os.path.join(static_dir, "admin", "admin.html")
    ]
    for p in check_files:
        if os.path.exists(p):
            return FileResponse(p, headers={"Cache-Control": "no-store"})
    return JSONResponse({"status": "error", "message": "Admin file not found"}, status_code=404)

# Умный роут для автоматического поиска файлов в корне static (airdrop, swap, style.css и т.д.)
@app.get("/{filename}")
async def serve_static_files(filename: str):
    static_dir = overlord.get_static_path()
    file_path = os.path.join(static_dir, filename)
    
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Поиск картинок, если запрашивают напрямую без /images/
    if filename.endswith(('.png', '.jpg', '.svg', '.ico', '.json')):
        img_path = os.path.join(static_dir, "images", filename)
        if os.path.exists(img_path): return FileResponse(img_path)
        manifest_path = os.path.join(static_dir, filename)
        if os.path.exists(manifest_path): return FileResponse(manifest_path)

    raise HTTPException(status_code=404)

# --- API ---

@app.get("/api/stats")
async def get_stats():
    try:
        db_stats = await get_stats_for_web() if DB_ENABLED else {}
        metrics = {
            'balance': f"{overlord.current_balance:.2f}",
            'traffic': round(random.uniform(400, 800), 2),
            'cpu': random.randint(20, 45),
            'ram': random.randint(60, 85),
            'ping': random.randint(15, 25),
            'connections': random.randint(800, 1200),
            'engine': {
                "core_id": overlord.core_id,
                "uptime": round(time.time() - overlord.session_start),
                "status": overlord.last_status
            }
        }
        if db_stats: metrics.update(db_stats)
        return metrics
    except Exception as e:
        return {"status": "error", "details": str(e)}

@app.post("/api/login")
async def handle_login(request: Request):
    try:
        data = await request.json()
        if str(data.get("login")) == overlord.admin_login and str(data.get("password")) == overlord.admin_pass:
            overlord.session_token = os.urandom(32).hex()
            res = JSONResponse({"status": "success"})
            res.set_cookie(key="auth_token", value=overlord.session_token, httponly=True, samesite="lax")
            return res
        return JSONResponse({"status": "error"}, status_code=401)
    except: return JSONResponse({"status": "error"}, status_code=400)

# --- MOUNT ---
app.mount("/static", StaticFiles(directory=overlord.get_static_path()), name="static")
log(f"STATIC: {overlord.get_static_path()} примонтирован", "INFO")

# --- CORE WORKER ---
async def core_worker():
    # Ожидание базы данных (максимум 5 попыток, чтобы не вешать сервер навсегда)
    retry = 0
    while DB_ENABLED and retry < 10:
        try:
            await init_db()
            log("DB: Connected Successfully", "SUCCESS")
            break
        except: 
            retry += 1
            log(f"DB: Waiting for connection (Attempt {retry}/10)...", "WARNING")
            await asyncio.sleep(5)

    while overlord.is_active:
        try:
            await overlord.update_config_from_db()
            
            if not overlord.mnemonic or not TON_ENABLED:
                overlord.last_status = "WAITING_CONFIG"
                await asyncio.sleep(10)
                continue

            async with LiteClient.from_mainnet_config() as client:
                mnemonic_list = overlord.mnemonic.split()
                if len(mnemonic_list) < 12:
                    overlord.last_status = "BAD_MNEMONIC"
                    log("Критическая ошибка: Мнемоника содержит менее 12 слов", "ERROR")
                    await asyncio.sleep(30); continue

                wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                overlord.last_status = "ACTIVE"
                log(f"CORE ACTIVE: {wallet.address}", "SUCCESS")
                
                while overlord.is_active:
                    try:
                        overlord.current_balance = (await wallet.get_balance()) / 1e9
                        old_mne = overlord.mnemonic
                        await overlord.update_config_from_db()
                        if overlord.mnemonic != old_mne:
                            log("CORE: Обнаружена новая мнемоника, перезапуск...", "WARNING")
                            break
                        await asyncio.sleep(30)
                    except Exception as e:
                        log(f"Heartbeat Error: {e}", "TRACE")
                        break
        except Exception as e:
            log(f"Global Loop Error: {e}", "ERROR")
            await asyncio.sleep(10)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Quantum Overlord запущен на порту {port}", "CORE")
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*", log_level="info")
