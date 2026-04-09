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
from fastapi import FastAPI, Request, Response
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
except ImportError:
    log("Критическая ошибка: pytoniq не найден!", "ERROR")
    sys.exit(1)

try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("L2: Модули базы данных подключены", "SUCCESS")
except ImportError:
    log("L2 ERROR: Файл database.py не найден!", "ERROR")
    sys.exit(1)

load_dotenv()

# --- УПРАВЛЕНИЕ ЯДРОМ ---
class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        # Настройки доступа
        self.admin_login = os.getenv("ADMIN_LOGIN", "1")
        self.admin_pass = os.getenv("ADMIN_PASS", "1")
        self.session_token = os.urandom(32).hex() 
        
        # Состояние системы
        self.pool_addr = None
        self.vault_ton = Address("UQBo0iou1BlB_8Xg0Hn_rUeIcrpyyhoboIauvnii889OFRoI")
        self.mnemonic = None
        self.ai_key = None
        self.strategy_level = 10
        
        self.pool_reserves = {"ton": "0.00", "token": "0.00"}
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        self.current_balance = 0.0

    def get_static_path(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        check_paths = [
            os.path.join(base_dir, 'static'),
            os.path.join(os.getcwd(), 'static'),
            '/app/static'
        ]
        for p in check_paths:
            if os.path.exists(p): return p
        return "static"

    async def update_config_from_db(self):
        try:
            cfg = await load_remote_config()
            if cfg:
                if cfg.get('mnemonic'):
                    self.mnemonic = " ".join(str(cfg.get('mnemonic')).replace('\n', ' ').split())
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

    async def fetch_neural_strategy(self, market_snapshot):
        if not self.ai_key: return {"cmd": "WAIT", "reason": "No AI Key"}
        try:
            client = openai.AsyncOpenAI(api_key=self.ai_key)
            res = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Analyze market. JSON ONLY: {\"cmd\": \"BUY\"/\"WAIT\", \"amt\": float, \"reason\": \"str\"}"},
                    {"role": "user", "content": json.dumps({"market": market_snapshot})}
                ],
                response_format={ "type": "json_object" },
                timeout=15
            )
            return json.loads(res.choices[0].message.content)
        except Exception as e:
            log(f"AI Neural Error: {e}", "ERROR")
            return {"cmd": "WAIT", "reason": "AI Error"}

    async def dispatch_hft_pulse(self, wallet, plan):
        if not self.pool_addr: return False
        try:
            amt = float(plan.get('amt', 0))
            if amt <= 0: return False
            nano_amt = int(amt * 1e9)
            
            swap_payload = (BeginCell()
                            .store_uint(0xea06185d, 32) 
                            .store_uint(int(time.time() + 300), 64) 
                            .store_coins(nano_amt)
                            .store_address(self.pool_addr)
                            .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
            
            await wallet.transfer(destination=self.vault_ton, amount=nano_amt + int(0.2e9), body=swap_payload)
            self.total_ops += 1
            log(f"ИМПУЛЬС ОТПРАВЛЕН: {amt} TON -> {plan.get('reason')}", "SUCCESS")
            return True
        except Exception as e:
            log(f"TON Pulse Error: {e}", "ERROR")
            return False

overlord = OmniNeuralOverlord()

@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(core_worker())
    yield
    overlord.is_active = False
    worker_task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- WEB ROUTES ---

@app.get("/")
@app.get("/index.html")
async def serve_index():
    return FileResponse(os.path.join(overlord.get_static_path(), "index.html"))

# УНИВЕРСАЛЬНЫЙ РОУТ ДЛЯ ВСЕХ ВАШИХ HTML (swap, forge, assets, staking)
@app.get("/{filename}.html")
async def serve_any_html(filename: str):
    static_dir = overlord.get_static_path()
    # Проверяем в корне static и в подпапке admin
    check_paths = [
        os.path.join(static_dir, f"{filename}.html"),
        os.path.join(static_dir, "admin", f"{filename}.html")
    ]
    for p in check_paths:
        if os.path.exists(p):
            return FileResponse(p)
    
    log(f"WEB ERROR: {filename}.html не найден", "WARNING")
    return JSONResponse({"detail": f"File {filename}.html not found"}, status_code=404)

@app.get("/admin")
@app.get("/admin/")
@app.get("/admin.html")
@app.get("/amin")
async def serve_admin(request: Request):
    token = request.cookies.get("auth_token")
    static_dir = overlord.get_static_path()
    
    # Если токен верный, ищем файл админки
    if token == overlord.session_token:
        paths = [
            os.path.join(static_dir, "admin", "admin.html"),
            os.path.join(static_dir, "admin", "index.html"),
            os.path.join(static_dir, "admin.html")
        ]
        for p in paths:
            if os.path.exists(p): return FileResponse(p)
        
        log(f"WEB ERROR: Admin file missing in {static_dir}", "ERROR")
        return JSONResponse({"detail": "Admin panel file missing"}, status_code=404)

    # Если не авторизован, показываем главную (вход)
    index_path = os.path.join(static_dir, "index.html")
    return FileResponse(index_path) if os.path.exists(index_path) else JSONResponse({"detail": "Index not found"}, status_code=404)

# --- API ENDPOINTS ---

@app.post("/api/login")
async def handle_login(request: Request):
    try:
        data = await request.json()
        if str(data.get("login")) == overlord.admin_login and str(data.get("password")) == overlord.admin_pass:
            overlord.session_token = os.urandom(32).hex()
            res = JSONResponse({"status": "success"})
            res.set_cookie(key="auth_token", value=overlord.session_token, httponly=True, samesite="lax")
            log(f"ADMIN: Вход выполнен успешно ({request.client.host})", "SUCCESS")
            return res
        return JSONResponse({"status": "error", "msg": "ACCESS DENIED"}, status_code=401)
    except: return JSONResponse({"status": "error"}, status_code=400)

@app.get("/api/stats")
async def get_stats(request: Request):
    if request.cookies.get("auth_token") != overlord.session_token:
        return JSONResponse({"status": "unauthorized"}, status_code=401)
    try:
        db_stats = await get_stats_for_web()
        db_stats.update({
            'balance': f"{overlord.current_balance:.2f}",
            'engine': {
                "core_id": overlord.core_id,
                "uptime": round(time.time() - overlord.session_start),
                "ops_total": overlord.total_ops,
                "status": overlord.last_status
            }
        })
        return db_stats
    except Exception as e: return {"status": "error", "msg": str(e)}

@app.post("/api/config")
async def save_config(request: Request):
    if request.cookies.get("auth_token") != overlord.session_token:
        return Response(status_code=401)
    try:
        data = await request.json()
        await update_remote_config(data)
        await overlord.update_config_from_db()
        return {"status": "success"}
    except Exception as e: return JSONResponse({"status": "error", "msg": str(e)}, status_code=400)

# --- STATIC MOUNTING (Для картинок и стилей) ---

static_path = overlord.get_static_path()
app.mount("/static", StaticFiles(directory=static_path), name="static")
app.mount("/images", StaticFiles(directory=os.path.join(static_path, "images")), name="images")

@app.get("/style.css")
async def serve_css():
    p = os.path.join(overlord.get_static_path(), "style.css")
    return FileResponse(p) if os.path.exists(p) else Response(status_code=404)

# --- CORE WORKER ---

async def core_worker():
    while True:
        try:
            await init_db()
            log("DB: Соединение установлено", "SUCCESS")
            break
        except: 
            log("DB: Ожидание PostgreSQL...", "WARNING")
            await asyncio.sleep(5)

    while overlord.is_active:
        try:
            await overlord.update_config_from_db()
            if not overlord.mnemonic:
                overlord.last_status = "WAITING_CONFIG"
                await asyncio.sleep(10); continue

            async with LiteClient.from_mainnet_config() as client:
                mnemonic_list = overlord.mnemonic.split()
                if len(mnemonic_list) < 12:
                    log("КРИТИЧЕСКИЙ СБОЙ: Мнемоника!", "ERROR")
                    await asyncio.sleep(20); continue

                wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                overlord.last_status = "ACTIVE"
                log(f"CORE: Wallet Linked -> {wallet.address}", "SUCCESS")
                
                while overlord.is_active:
                    try:
                        await client.reconnect()
                        overlord.current_balance = (await wallet.get_balance()) / 1e9
                        market_state = await get_market_state()
                        plan = await overlord.fetch_neural_strategy(market_state)
                        
                        if plan.get('cmd') == "BUY" and overlord.current_balance > (float(plan.get('amt', 0)) + 0.5):
                            if await overlord.dispatch_hft_pulse(wallet, plan):
                                await log_ai_action(plan, market_state.get('current_metrics', {}))
                        
                        await asyncio.sleep(30)
                    except Exception as e:
                        log(f"Pulse Error: {e}", "TRACE")
                        await asyncio.sleep(10); break
        except Exception as e:
            log(f"Fatal Core: {e}", "ERROR")
            await asyncio.sleep(10)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Quantum Overlord запущен на порту {port}", "CORE")
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*", log_level="error")
