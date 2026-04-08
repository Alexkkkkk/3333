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

# FastAPI для стабильной работы веб-интерфейса
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- СИСТЕМА ЛОГИРОВАНИЯ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {
        "INFO": "\033[94m", "SUCCESS": "\033[92m", 
        "WARNING": "\033[93m", "ERROR": "\033[91m", 
        "CORE": "\033[95m", "TRACE": "\033[90m"
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    print(f"{color}[{timestamp}] [{level}] {message}{reset}", flush=True)

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

    def _clean_string(self, text):
        if not text: return ""
        return "".join(char for char in str(text) if ord(char) < 128).strip()

    def get_static_path(self):
        """Определяет путь к папке static."""
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
            if cfg and cfg.get('mnemonic'):
                raw_mnemonic = str(cfg.get('mnemonic', ''))
                self.mnemonic = " ".join(raw_mnemonic.replace('\n', ' ').replace('\r', ' ').split())
                self.ai_key = self._clean_string(cfg.get('ai_api_key', ''))
                pool_raw = self._clean_string(cfg.get('token_pool_address', cfg.get('dedust_pool', '')))
                if pool_raw: 
                    try: self.pool_addr = Address(pool_raw)
                    except: log(f"Ошибка формата пула: {pool_raw}", "WARNING")
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                return True
            return False
        except Exception as e:
            log(f"Ошибка конфига: {e}", "ERROR")
            return False

# Глобальный объект управления
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
    try:
        await worker_task
    except asyncio.CancelledError:
        log("CORE: Воркер успешно остановлен", "SUCCESS")

app = FastAPI(title="Quantum Omni Overlord", lifespan=lifespan)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- WEB ROUTES (МАРШРУТЫ АДМИНКИ) ---

@app.get("/")
@app.get("/index.html")
async def serve_index():
    path = os.path.join(overlord.get_static_path(), "index.html")
    return FileResponse(path)

@app.get("/tonconnect-manifest.json")
async def serve_manifest():
    path = os.path.join(overlord.get_static_path(), "tonconnect-manifest.json")
    if os.path.exists(path): return FileResponse(path)
    return JSONResponse({"status": "error"}, status_code=404)

@app.get("/admin")
@app.get("/amin") # Обработка опечатки
@app.get("/admin/admin.html")
async def serve_admin(request: Request):
    # Проверка авторизации через куки
    if request.cookies.get("auth_token") == overlord.session_token:
        admin_path = os.path.join(overlord.get_static_path(), "admin", "admin.html")
        if not os.path.exists(admin_path):
             admin_path = os.path.join(overlord.get_static_path(), "admin", "index.html")
        
        if os.path.exists(admin_path):
            return FileResponse(admin_path)
        return JSONResponse({"error": "Admin page not found in static/admin/"}, status_code=404)
    
    # Если не авторизован - на главную
    return FileResponse(os.path.join(overlord.get_static_path(), "index.html"))

# --- API ROUTES ---

@app.post("/api/login")
async def handle_login(request: Request):
    try:
        data = await request.json()
        if str(data.get("login")) == overlord.admin_login and str(data.get("password")) == overlord.admin_pass:
            res = JSONResponse({"status": "success", "token": overlord.session_token})
            # HttpOnly для защиты от XSS
            res.set_cookie(
                key="auth_token", 
                value=overlord.session_token, 
                max_age=86400, 
                httponly=True, 
                samesite='lax'
            )
            log(f"AUTH: Вход выполнен ({request.client.host})", "SUCCESS")
            return res
        return JSONResponse({"status": "error", "msg": "INVALID ACCESS KEY"}, status_code=401)
    except:
        return JSONResponse({"status": "error", "msg": "BAD REQUEST"}, status_code=400)

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
                "ops_total": overlord.total_ops,
                "uptime": round(time.time() - overlord.session_start),
                "last_status": overlord.last_status
            }
        })
        return db_stats
    except Exception as e:
        return JSONResponse({"status": "error", "msg": str(e)})

@app.post("/api/config")
async def handle_update_config(request: Request):
    if request.cookies.get("auth_token") != overlord.session_token:
        return JSONResponse({"status": "unauthorized"}, status_code=401)
    try:
        data = await request.json()
        await update_remote_config(data)
        await overlord.update_config_from_db()
        return {"status": "success"}
    except Exception as e:
        return JSONResponse({"status": "error", "msg": str(e)}, status_code=400)

# Монтирование статических файлов
static_path = overlord.get_static_path()
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Дополнительное монтирование для картинок и админ-ресурсов
if os.path.exists(os.path.join(static_path, "images")):
    app.mount("/images", StaticFiles(directory=os.path.join(static_path, "images")), name="images")
if os.path.exists(os.path.join(static_path, "admin")):
    app.mount("/admin/static", StaticFiles(directory=os.path.join(static_path, "admin")), name="admin_static")

# --- CORE LOGIC (ВОРКЕР) ---

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
        
        # DeDust Swap Payload
        payload = (BeginCell()
                  .store_uint(0xea06185d, 32) 
                  .store_uint(int(time.time() + 300), 64)
                  .store_coins(nano_amt)
                  .store_address(overlord.pool_addr)
                  .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
        
        await wallet.transfer(destination=overlord.vault_ton, amount=nano_amt + int(0.2e9), body=payload)
        overlord.total_ops += 1
        log(f"ИМПУЛЬС: Выполнена транзакция на {amt} TON", "SUCCESS")
        return True
    except Exception as e:
        log(f"TON СБОЙ: {e}", "ERROR")
        return False

async def core_worker():
    """Фоновый воркер для работы с блокчейном и ИИ."""
    while True:
        try:
            await init_db()
            log("DB: Соединение с PostgreSQL активно", "SUCCESS")
            break
        except:
            log("DB: Ожидание PostgreSQL...", "WARNING")
            await asyncio.sleep(5)

    while overlord.is_active:
        try:
            # Обновляем конфиг из БД перед каждой сессией
            if not await overlord.update_config_from_db():
                overlord.last_status = "WAITING_CONFIG"
                await asyncio.sleep(10); continue

            async with LiteClient.from_mainnet_config() as client:
                mnemonic_list = overlord.mnemonic.split()
                if len(mnemonic_list) < 12:
                    log("MNEMONIC ERROR: Некорректная фраза", "ERROR")
                    await asyncio.sleep(30); continue

                wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                overlord.last_status = "ACTIVE"
                log(f"TON: Воркер запущен. Адрес: {wallet.address}", "SUCCESS")
                
                while overlord.is_active:
                    try:
                        await client.reconnect()
                        market_state = await get_market_state()
                        
                        try:
                            balance_nano = await asyncio.wait_for(wallet.get_balance(), timeout=15.0)
                            overlord.current_balance = balance_nano / 1e9
                        except:
                            log("TON Node Timeout. Переподключение...", "WARNING")
                            break

                        plan = await fetch_neural_strategy(market_state)
                        
                        # Условие покупки: есть команда BUY и баланс позволяет (сумма + запас на газ)
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

# --- ТОЧКА ВХОДА ---
if __name__ == "__main__":
    # Читаем порт из переменной окружения (важно для Docker/Hosting)
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Старт Quantum Overlord на порту {port}", "CORE")
    
    # Запуск сервера uvicorn
    # 'main:app' означает, что этот файл должен называться main.py
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info", proxy_headers=True)
