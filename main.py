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

# --- УЛУЧШЕННАЯ СИСТЕМА ЛОГИРОВАНИЯ ---
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
    except:
        pass

# --- УЛЬТРА-ЗАЩИЩЕННЫЙ ИМПОРТ TON ---
log(">>> ИНИЦИАЛИЗАЦИЯ ЯДРА QUANTUM (FASTAPI HYBRID) <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address, begin_cell as BeginCell
    log("L1: Библиотеки TON загружены (pytoniq)", "SUCCESS")
except ImportError:
    try:
        from pytoniq import LiteClient, WalletV4R2, Address
        from pytoniq_core import BeginCell
        log("L1: Загрузка через pytoniq_core", "SUCCESS")
    except ImportError:
        log("Критическая ошибка: pytoniq не найден!", "ERROR")
        sys.exit(1)

try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("L2: Модули базы данных подключены", "SUCCESS")
except ImportError:
    log("L2 ERROR: database.py не найден в корне проекта!", "ERROR")
    sys.exit(1)

load_dotenv()

# --- КЛАСС УПРАВЛЕНИЯ ЯДРОМ ---
class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        # Настройки доступа
        self.admin_login = os.getenv("ADMIN_LOGIN", "admin")
        self.admin_pass = os.getenv("ADMIN_PASS", "quantum2026")
        self.session_token = os.urandom(32).hex() 
        
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

    def get_logo_url(self):
        return "/static/images/logo.png"

    async def update_config_from_db(self):
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                raw_mnemonic = str(cfg.get('mnemonic', ''))
                self.mnemonic = " ".join(raw_mnemonic.replace('\n', ' ').replace('\r', ' ').split())
                self.ai_key = "".join(c for c in str(cfg.get('ai_api_key', '')) if ord(c) < 128).strip()
                pool_raw = str(cfg.get('token_pool_address', cfg.get('dedust_pool', ''))).strip()
                if pool_raw: 
                    try: self.pool_addr = Address(pool_raw)
                    except: log(f"Ошибка формата пула: {pool_raw}", "WARNING")
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                return True
            return False
        except Exception as e:
            log(f"Ошибка конфига: {e}", "ERROR")
            return False

overlord = OmniNeuralOverlord()

# --- FASTAPI LIFE-CYCLE ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log("CORE: Запуск воркера нейросети и TON...", "CORE")
    worker_task = asyncio.create_task(core_worker())
    yield
    log("CORE: Завершение работы системы...", "WARNING")
    overlord.is_active = False
    worker_task.cancel()
    try: await worker_task
    except asyncio.CancelledError: log("CORE: Воркер остановлен", "SUCCESS")

app = FastAPI(title="Quantum Omni Overlord", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- WEB ROUTES ---

@app.get("/")
@app.get("/index.html")
async def serve_index():
    path = os.path.join(overlord.get_static_path(), "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({"error": "Index file missing"}, status_code=404)

# Прямой проброс для логотипа (убирает 404 в логах)
@app.get("/images/logo.png")
async def serve_logo_direct():
    static_dir = overlord.get_static_path()
    logo_path = os.path.join(static_dir, "images", "logo.png")
    if os.path.exists(logo_path):
        return FileResponse(logo_path)
    return JSONResponse({"error": "Logo file missing"}, status_code=404)

# Прямой проброс для фавиконки
@app.get("/favicon.ico")
async def serve_favicon():
    fav_path = os.path.join(overlord.get_static_path(), "favicon.ico")
    if os.path.exists(fav_path):
        return FileResponse(fav_path)
    return Response(status_code=204)

# Динамический роут для всех страниц (swap.html, assets.html и т.д.)
@app.get("/{page_name}.html")
async def serve_any_page(page_name: str):
    path = os.path.join(overlord.get_static_path(), f"{page_name}.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({"error": "Page not found"}, status_code=404)

# Прямой проброс для CSS
@app.get("/style.css")
async def serve_css():
    return FileResponse(os.path.join(overlord.get_static_path(), "style.css"))

@app.get("/api/config")
async def get_web_config():
    return {
        "logo": overlord.get_logo_url(),
        "project_name": "QUANCORE",
        "version": "V4.1",
        "core_id": overlord.core_id
    }

@app.post("/api/connect")
async def handle_wallet_connect(request: Request):
    try:
        data = await request.json()
        address = data.get("address")
        log(f"NETWORK: Оператор подключен -> {address[:10]}...", "SUCCESS")
        return {"status": "success", "sync": True, "core": overlord.core_id}
    except:
        return JSONResponse({"status": "error"}, status_code=400)

# --- ADMIN PANEL LOGIC ---

@app.get("/admin")
@app.get("/admin/")
async def serve_admin_root(request: Request):
    token = request.cookies.get("auth_token")
    no_cache_headers = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    
    if token and token == overlord.session_token:
        static_dir = overlord.get_static_path()
        admin_file = os.path.join(static_dir, "admin", "admin.html")
        if not os.path.exists(admin_file):
            admin_file = os.path.join(static_dir, "admin.html")
            
        if os.path.exists(admin_file):
            return FileResponse(admin_file, headers=no_cache_headers)
        return JSONResponse({"error": "Admin UI not found"}, status_code=404)
            
    return FileResponse(os.path.join(overlord.get_static_path(), "index.html"), headers=no_cache_headers)

@app.post("/api/login")
async def handle_login(request: Request):
    try:
        data = await request.json()
        if str(data.get("login")) == overlord.admin_login and str(data.get("password")) == overlord.admin_pass:
            overlord.session_token = os.urandom(32).hex()
            res = JSONResponse({"status": "success", "token": overlord.session_token})
            res.set_cookie(key="auth_token", value=overlord.session_token, max_age=3600, httponly=True, samesite='lax')
            log(f"AUTH: Вход выполнен ({request.client.host})", "SUCCESS")
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
            'pool_info': {
                "address": str(overlord.pool_addr) if overlord.pool_addr else "NOT CONFIGURED",
                "reserve_ton": overlord.pool_reserves["ton"],
                "status": "SYNCED" if overlord.pool_addr else "WAITING"
            },
            'engine': {
                "core_id": overlord.core_id, 
                "uptime": round(time.time() - overlord.session_start),
                "last_status": overlord.last_status, 
                "logo_path": overlord.get_logo_url(),
                "ops_total": overlord.total_ops
            }
        })
        return db_stats
    except Exception as e: return JSONResponse({"status": "error", "msg": str(e)})

# --- МОНТИРОВАНИЕ СТАТИКИ ---
static_path = overlord.get_static_path()
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    log(f"SYSTEM: Статика смонтирована из {static_path}", "INFO")
else:
    log(f"SYSTEM ERROR: Папка статики не найдена!", "ERROR")

# --- CORE LOGIC ---

async def fetch_neural_strategy(market_snapshot):
    if not overlord.ai_key: return {"cmd": "WAIT", "reason": "No AI Key"}
    try:
        client = openai.AsyncOpenAI(api_key=overlord.ai_key)
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
        log(f"AI ERROR: {e}", "ERROR")
        return {"cmd": "WAIT", "reason": "AI Error"}

async def dispatch_hft_pulse(wallet, plan):
    if not overlord.pool_addr: return False
    try:
        amt = float(plan.get('amt', 0))
        if amt <= 0: return False
        nano_amt = int(amt * 1e9)
        payload = (BeginCell()
                  .store_uint(0xea06185d, 32) 
                  .store_uint(int(time.time() + 300), 64)
                  .store_coins(nano_amt)
                  .store_address(overlord.pool_addr)
                  .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
        await wallet.transfer(destination=overlord.vault_ton, amount=nano_amt + int(0.2e9), body=payload)
        overlord.total_ops += 1
        log(f"ИМПУЛЬС: Отправлено {amt} TON", "SUCCESS")
        return True
    except Exception as e:
        log(f"TON ERROR: {e}", "ERROR")
        return False

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
            if not await overlord.update_config_from_db():
                overlord.last_status = "WAITING_CONFIG"
                await asyncio.sleep(10); continue

            async with LiteClient.from_mainnet_config() as client:
                if not overlord.mnemonic or len(overlord.mnemonic.split()) < 12:
                    overlord.last_status = "BAD_MNEMONIC"
                    await asyncio.sleep(30); continue

                wallet = await WalletV4R2.from_mnemonic(client, overlord.mnemonic.split())
                overlord.last_status = "ACTIVE"
                log(f"TON: Система активна. Адрес: {wallet.address}", "SUCCESS")
                
                while overlord.is_active:
                    try:
                        market_state = await get_market_state()
                        balance_nano = await asyncio.wait_for(wallet.get_balance(), timeout=15.0)
                        overlord.current_balance = balance_nano / 1e9
                        
                        plan = await fetch_neural_strategy(market_state)
                        if plan.get('cmd') == "BUY" and overlord.current_balance > (float(plan.get('amt', 0)) + 0.5):
                            if await dispatch_hft_pulse(wallet, plan):
                                await log_ai_action(plan, market_state.get('current_metrics', {}))
                        
                        await asyncio.sleep(30)
                    except Exception as inner_e:
                        log(f"ITERATION ERROR: {inner_e}", "TRACE")
                        await asyncio.sleep(10); break 
        except Exception as e:
            log(f"FATAL CORE: {e}", "ERROR")
            await asyncio.sleep(10)

if __name__ == "__main__":
    # Читаем порт из переменной окружения Bothost
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Старт Quantum Overlord на порту {port}", "CORE")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info", proxy_headers=True)
