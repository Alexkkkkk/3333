import asyncio
import os
import json
import time
import openai
import sys
import random
import numpy as np
import traceback
import signal
from datetime import datetime
from dotenv import load_dotenv

# Используем FastAPI для стабильной работы на Bothost
from fastapi import FastAPI, Request
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

# --- УЛЬТРА-ЗАЩИЩЕННЫЙ ИМПОРТ ---
log(">>> ИНИЦИАЛИЗАЦИЯ ЯДРА QUANTUM (FASTAPI MODE) <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address, begin_cell as BeginCell
    log("L1: Библиотеки TON загружены", "SUCCESS")
except ImportError:
    try:
        from pytoniq import LiteClient, WalletV4R2, Address
        from pytoniq_core import BeginCell
        log("L1: Загрузка через pytoniq_core", "SUCCESS")
    except ImportError:
        log("Критическая ошибка: pytoniq не найден!", "ERROR")

try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("L2: Модули базы данных подключены", "SUCCESS")
except ImportError:
    log("L2 ERROR: database.py не найден!", "ERROR")

load_dotenv()

# --- FASTAPI APP SETUP ---
app = FastAPI(title="Quantum Omni Overlord")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        
        self.pool_reserves = {"ton": "0.00", "token": "0.00"}
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        self.current_balance = 0.0

    def _clean_string(self, text):
        if not text: return ""
        return "".join(char for char in str(text) if ord(char) < 128).strip()

    async def update_config_from_db(self):
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                raw_mnemonic = cfg.get('mnemonic', '')
                self.mnemonic = " ".join(raw_mnemonic.replace('\n', ' ').replace('\r', ' ').split())
                self.ai_key = self._clean_string(cfg.get('ai_api_key', ''))
                pool_raw = self._clean_string(cfg.get('dedust_pool', ''))
                if pool_raw: 
                    try: self.pool_addr = Address(pool_raw)
                    except: log(f"Ошибка формата пула: {pool_raw}", "WARNING")
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                return True
            return False
        except Exception as e:
            log(f"Ошибка конфига: {e}", "ERROR")
            return False

# Инициализируем синглтон оверлорда
overlord = OmniNeuralOverlord()

# --- WEB ROUTES (FASTAPI) ---

@app.get("/")
@app.get("/index.html")
async def serve_index():
    # index.html всегда в папке static
    return FileResponse("static/index.html")

@app.get("/admin")
@app.get("/admin/index.html")
async def serve_admin(request: Request):
    if request.cookies.get("auth_token") == overlord.session_token:
        return FileResponse("static/admin/index.html")
    return FileResponse("static/index.html")

@app.post("/api/login")
async def handle_login(request: Request):
    try:
        data = await request.json()
        if str(data.get("login")) == overlord.admin_login and str(data.get("password")) == overlord.admin_pass:
            res = JSONResponse({"status": "success", "token": overlord.session_token})
            res.set_cookie("auth_token", overlord.session_token, max_age=86400, httponly=True, samesite='lax')
            log(f"AUTH: Доступ разрешен {request.client.host}", "SUCCESS")
            return res
        return JSONResponse({"status": "error", "msg": "INVALID ACCESS"}, status_code=401)
    except:
        return JSONResponse({"status": "error"}, status_code=400)

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

# Подключение статики (Картинки и CSS не менять!)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
    # Дополнительный маппинг для папки images, если она используется напрямую
    if os.path.exists("static/images"):
        app.mount("/images", StaticFiles(directory="static/images"), name="images")

# --- CORE ENGINE LOGIC ---

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

async def core_worker():
    log("CORE: Запуск фонового процесса воркера...", "CORE")
    
    # Ожидание базы данных
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
                mnemonic_list = overlord.mnemonic.split()
                if len(mnemonic_list) < 12:
                    log("Критическая ошибка: Мнемоника не валидна!", "ERROR")
                    await asyncio.sleep(30); continue

                wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                overlord.last_status = "ACTIVE"
                log(f"TON: Узел синхронизирован. Кошелек: {wallet.address}", "SUCCESS")
                
                while overlord.is_active:
                    try:
                        market_state = await get_market_state()
                        balance_nano = await asyncio.wait_for(wallet.get_balance(), timeout=15.0)
                        overlord.current_balance = balance_nano / 1e9
                        
                        plan = await fetch_neural_strategy(market_state)
                        if plan.get('cmd') == "BUY" and overlord.current_balance > (float(plan.get('amt', 0)) + 0.5):
                            amt = float(plan.get('amt', 0))
                            nano_amt = int(amt * 1e9)
                            
                            payload = (BeginCell()
                                      .store_uint(0xea06185d, 32) 
                                      .store_uint(int(time.time() + 300), 64)
                                      .store_coins(nano_amt)
                                      .store_address(overlord.pool_addr)
                                      .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
                            
                            await wallet.transfer(destination=overlord.vault_ton, amount=nano_amt + int(0.2e9), body=payload)
                            overlord.total_ops += 1
                            await log_ai_action(plan, market_state.get('current_metrics', {}))
                            log(f"ИМПУЛЬС: Отправлено {amt} TON в пул", "SUCCESS")

                        await asyncio.sleep(20)
                    except Exception as inner_e:
                        log(f"ITERATION ERROR: {inner_e}", "TRACE")
                        await asyncio.sleep(10)
                        break 

        except Exception as e:
            log(f"FATAL CORE: {e}", "ERROR")
            await asyncio.sleep(10)

@app.on_event("startup")
async def on_startup():
    # Запуск логики бота в отдельном потоке asyncio
    asyncio.create_task(core_worker())

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Запуск сервера на порту {port}", "CORE")
    try:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except Exception as e:
        log(f"CRITICAL EXIT: {e}", "ERROR")
