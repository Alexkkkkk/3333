import asyncio
import os
import json
import time
import sys
import signal
import traceback
from datetime import datetime
from dotenv import load_dotenv

# Используем FastAPI, так как Bothost настроен под него (судя по логам uvicorn)
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- СИСТЕМА УЛЬТРА-ЛОГИРОВАНИЯ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    colors = {
        "INFO": "\033[94m", "SUCCESS": "\033[92m", 
        "WARNING": "\033[93m", "ERROR": "\033[91m", 
        "CORE": "\033[95m", "TRACE": "\033[90m", "WEB": "\033[36m"
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    print(f"{color}[{timestamp}] [{level}] {message}{reset}", flush=True)

log(">>> ЗАПУСК СИСТЕМЫ NEURAL SENTINEL V3 <<<", "CORE")

# --- ПРОВЕРКА ОКРУЖЕНИЯ ---
try:
    from pytoniq import LiteClient, WalletV4R2
    from database import (init_db, get_stats_for_web, load_remote_config)
    log("L1: Библиотеки TON и модули БД загружены", "SUCCESS")
except ImportError as e:
    log(f"L1 ERROR: Ошибка импорта: {e}", "ERROR")
    # Не выходим сразу, чтобы uvicorn успел поднять сервер и показать логи

load_dotenv()

# --- ИНИЦИАЛИЗАЦИЯ FASTAPI ---
app = FastAPI(title="Neural Sentinel Terminal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SentinelState:
    def __init__(self):
        self.is_active = True
        self.current_balance = 0.0
        self.total_ops = 0
        self.last_status = "BOOTING"
        self.core_id = f"SENTINEL-{os.urandom(2).hex().upper()}"
        self.mnemonic = None
        self.target_pool = None
        self.ai_key = None

state = SentinelState()

# --- WEB HANDLERS (FASTAPI) ---

@app.get("/")
@app.get("/index.html")
async def serve_index():
    path = os.path.join("static", "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({"status": "error", "message": "index.html not found"}, status_code=404)

@app.get("/admin")
async def serve_admin():
    path = os.path.join("static", "admin", "admin.html")
    if os.path.exists(path):
        return FileResponse(path)
    return FileResponse(os.path.join("static", "index.html"))

@app.get("/api/stats")
async def get_stats():
    try:
        db_stats = await get_stats_for_web()
    except:
        db_stats = {}
    
    return {
        "balance": f"{state.current_balance:.2f}",
        "engine": {
            "core_id": state.core_id,
            "last_status": state.last_status,
            "ops_total": state.total_ops
        },
        "pool_info": {
            "address": state.target_pool or "NOT CONFIGURED",
            "reserve_ton": db_stats.get("reserve_ton", "0.00"),
            "status": "STABLE" if state.is_active else "HALTED"
        }
    }

# Подключаем статику для дизайна и картинок
static_path = os.path.join(os.getcwd(), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    log(f"FS: Статика подключена из {static_path}", "TRACE")
    
    # Прямой маппинг для папки images (твои логотипы и картинки)
    img_path = os.path.join(static_path, "images")
    if os.path.exists(img_path):
        app.mount("/images", StaticFiles(directory=img_path), name="images")

# --- CORE LOGIC (RUNNING IN BACKGROUND) ---

async def core_loop():
    log("CORE: Запуск системных процессов в фоне...", "INFO")
    
    # Ожидание базы
    while True:
        try:
            await init_db()
            log("DB: Связь с PostgreSQL установлена", "SUCCESS")
            break
        except Exception as e:
            log(f"DB: Ошибка подключения: {e}. Повтор через 5с...", "WARNING")
            await asyncio.sleep(5)

    while state.is_active:
        try:
            # Загрузка конфигурации
            cfg = await load_remote_config()
            if cfg:
                state.mnemonic = cfg.get('mnemonic', state.mnemonic)
                state.ai_key = cfg.get('ai_api_key', state.ai_key)
                state.target_pool = cfg.get('dedust_pool', state.target_pool)

            if not state.mnemonic:
                state.last_status = "WAITING_CONFIG"
                await asyncio.sleep(10)
                continue

            # Работа с TON
            async with LiteClient.from_mainnet_config() as client:
                wallet = await WalletV4R2.from_mnemonic(client, state.mnemonic.split())
                state.last_status = "ACTIVE"
                log(f"TON: Узел {wallet.address} синхронизирован", "SUCCESS")
                
                while state.is_active:
                    try:
                        balance_nano = await asyncio.wait_for(wallet.get_balance(), timeout=10.0)
                        state.current_balance = balance_nano / 1e9
                        log(f"MONITOR: Баланс {state.current_balance:.2f} TON", "TRACE")
                        await asyncio.sleep(30)
                    except Exception as e:
                        log(f"LOOP: Ошибка мониторинга: {e}", "WARNING")
                        await asyncio.sleep(5)
                        break # Переподключение LiteClient

        except Exception as e:
            log(f"CRITICAL: Сбой в ядре: {e}", "ERROR")
            state.last_status = "RECOVERY"
            await asyncio.sleep(10)

@app.on_event("startup")
async def startup_event():
    # Запускаем основной цикл бота как фоновую задачу FastAPI
    asyncio.create_task(core_loop())

# --- RUNNER ---

if __name__ == "__main__":
    # Получаем порт от Bothost (важно для работы внешнего адреса)
    port = int(os.getenv("PORT", 3000))
    host = "0.0.0.0"
    
    log(f"SERVER: Попытка запуска терминала на {host}:{port}", "CORE")
    
    try:
        # Запуск сервера uvicorn
        uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)
    except (KeyboardInterrupt, SystemExit):
        log("SYSTEM: Работа завершена пользователем.", "INFO")
        state.is_active = False
    except Exception as e:
        log(f"SYSTEM FATAL: {e}\n{traceback.format_exc()}", "ERROR")
