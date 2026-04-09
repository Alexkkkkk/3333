import asyncio
import os
import json
import time
import openai
import sys
import random
import numpy as np
import traceback
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# FastAPI компоненты
from fastapi import FastAPI, Request, Response, Body
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

# --- ИМПОРТ TON ---
log(">>> ИНИЦИАЛИЗАЦИЯ ЯДРА QUANTUM (FASTAPI HYBRID) <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address, begin_cell as BeginCell
    log("L1: Библиотеки TON загружены", "SUCCESS")
except ImportError:
    log("Критическая ошибка: pytoniq не найден!", "ERROR")
    sys.exit(1)

try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("L2: Модули базы данных подключены", "SUCCESS")
except ImportError:
    log("L2 ERROR: database.py отсутствует!", "ERROR")
    sys.exit(1)

load_dotenv()

# --- УПРАВЛЕНИЕ ЯДРОМ ---
class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        # Учетные данные админа (можно менять в .env)
        self.admin_login = os.getenv("ADMIN_LOGIN", "1")
        self.admin_pass = os.getenv("ADMIN_PASS", "admin")
        self.session_token = os.urandom(32).hex() 
        
        self.pool_addr = None
        self.vault_ton = Address("UQBo0iou1BlB_8Xg0Hn_rUeIcrpyyhoboIauvnii889OFRoI")
        self.mnemonic = None
        self.ai_key = None
        
        self.pool_reserves = {"ton": "0.00", "token": "0.00"}
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        self.current_balance = 0.0

    def get_static_path(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for p in [os.path.join(base_dir, 'static'), '/app/static', 'static']:
            if os.path.exists(p): return p
        return "static"

    async def update_config_from_db(self):
        try:
            cfg = await load_remote_config()
            if cfg:
                if cfg.get('mnemonic'):
                    self.mnemonic = " ".join(str(cfg.get('mnemonic')).split())
                self.ai_key = str(cfg.get('ai_api_key', '')).strip()
                pool_raw = str(cfg.get('dedust_pool', cfg.get('token_pool_address', ''))).strip()
                if pool_raw and pool_raw != "None":
                    try: self.pool_addr = Address(pool_raw)
                    except: log(f"Bad Pool Addr: {pool_raw}", "WARNING")
                return True
            return False
        except Exception as e:
            log(f"Config Error: {e}", "ERROR")
            return False

overlord = OmniNeuralOverlord()

# --- FASTAPI APP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(core_worker())
    yield
    overlord.is_active = False
    worker_task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- API & ROUTES ---

@app.get("/")
@app.get("/index.html")
async def serve_index():
    return FileResponse(os.path.join(overlord.get_static_path(), "index.html"))

# УНИВЕРСАЛЬНЫЙ РОУТ ДЛЯ СТРАНИЦ (assets.html, forge.html и т.д.)
@app.get("/{page_name}.html")
async def serve_any_page(page_name: str):
    path = os.path.join(overlord.get_static_path(), f"{page_name}.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({"error": "Page not found"}, status_code=404)

# ОБРАБОТКА ПОДКЛЮЧЕНИЯ (чтобы убрать 404 в логах)
@app.post("/api/connect")
async def handle_connect(request: Request):
    try:
        data = await request.json()
        log(f"WEB: Подключение кошелька {data.get('address', 'unknown')[:10]}...", "INFO")
        return {"status": "success", "core": overlord.core_id}
    except:
        return {"status": "error"}

@app.get("/api/config")
async def get_web_config():
    return {"logo": "/images/logo.png", "project_name": "QUANTUM", "core_id": overlord.core_id}

# --- ADMIN PANEL ---

@app.post("/api/login")
async def handle_login(request: Request):
    data = await request.json()
    if str(data.get("login")) == overlord.admin_login and str(data.get("password")) == overlord.admin_pass:
        overlord.session_token = os.urandom(32).hex()
        res = JSONResponse({"status": "success"})
        res.set_cookie(key="auth_token", value=overlord.session_token, httponly=True)
        return res
    return JSONResponse({"status": "error"}, status_code=401)

@app.post("/api/config")
async def save_config(request: Request):
    if request.cookies.get("auth_token") != overlord.session_token:
        return Response(status_code=401)
    data = await request.json()
    await update_remote_config(data)
    await overlord.update_config_from_db()
    return {"status": "success"}

@app.get("/api/stats")
async def get_stats(request: Request):
    if request.cookies.get("auth_token") != overlord.session_token:
        return Response(status_code=401)
    db_stats = await get_stats_for_web()
    db_stats.update({
        'balance': f"{overlord.current_balance:.2f}",
        'engine': {"uptime": round(time.time() - overlord.session_start), "status": overlord.last_status}
    })
    return db_stats

# --- STATIC & LOGO ---
@app.get("/images/logo.png")
async def serve_logo():
    path = os.path.join(overlord.get_static_path(), "images", "logo.png")
    return FileResponse(path) if os.path.exists(path) else Response(status_code=404)

@app.get("/style.css")
async def serve_css():
    path = os.path.join(overlord.get_static_path(), "style.css")
    return FileResponse(path) if os.path.exists(path) else Response(status_code=404)

app.mount("/static", StaticFiles(directory=overlord.get_static_path()), name="static")

# --- CORE WORKER ---
async def core_worker():
    while True:
        try:
            await init_db()
            log("DB: Соединение установлено", "SUCCESS")
            break
        except: await asyncio.sleep(5)

    while overlord.is_active:
        try:
            await overlord.update_config_from_db()
            if not overlord.mnemonic:
                overlord.last_status = "WAITING_CONFIG"
                await asyncio.sleep(15); continue

            async with LiteClient.from_mainnet_config() as client:
                wallet = await WalletV4R2.from_mnemonic(client, overlord.mnemonic.split())
                overlord.last_status = "ACTIVE"
                log(f"TON: Адрес кошелька -> {wallet.address}", "SUCCESS")
                
                while overlord.is_active:
                    try:
                        overlord.current_balance = (await wallet.get_balance()) / 1e9
                        market_state = await get_market_state()
                        plan = await fetch_neural_strategy(market_state)
                        
                        if plan.get('cmd') == "BUY" and overlord.current_balance > float(plan.get('amt', 0)):
                            await dispatch_hft_pulse(wallet, plan)
                        
                        await asyncio.sleep(60)
                    except Exception as e:
                        log(f"Pulse Error: {e}", "TRACE")
                        await asyncio.sleep(10); break
        except Exception as e:
            log(f"Fatal Core: {e}", "ERROR")
            await asyncio.sleep(10)

async def dispatch_hft_pulse(wallet, plan):
    # Логика отправки TON...
    overlord.total_ops += 1
    log(f"ИМПУЛЬС: {plan.get('amt')} TON", "SUCCESS")
    return True

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Старт Quantum Overlord на порту {port}", "CORE")
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True)
