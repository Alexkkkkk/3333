import asyncio
import os
import json
import time
import sys
import random
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

# Импорт функций из твоего модуля database.py
from database import (
    init_db, get_stats_for_web, register_visit, 
    save_wallet_state, log_ai_action, update_remote_config, 
    load_remote_config
)

load_dotenv()

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
    log_msg = f"[{timestamp}] [{level}] {message}"
    print(f"{color}{log_msg}{reset}", flush=True)

# --- ИНИЦИАЛИЗАЦИЯ TON ЯДРА ---
log(">>> ЗАПУСК ГИБРИДНОГО ЯДРА QUANTUM V4.1 + POSTGRES ANALYTICS <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    log("L1: Библиотеки TON (pytoniq) загружены", "SUCCESS")
    TON_ENABLED = True
except ImportError:
    log("Критическая ошибка: pytoniq не найден!", "ERROR")
    TON_ENABLED = False

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"QC-CORE-{os.urandom(2).hex().upper()}"
        
        # Настройки безопасности
        self.admin_login = os.getenv("ADMIN_LOGIN", "admin")
        self.admin_pass = os.getenv("ADMIN_PASS", "quantum2026")
        self.session_token = os.urandom(32).hex() 
        
        self.mnemonic = None
        self.last_status = "INITIALIZING"
        self.current_balance = 0.0

    def get_static_path(self):
        """Определение пути к папке static согласно структуре проекта."""
        # Проверка стандартного пути в Docker и локально
        paths_to_check = ["/app/static", "./static", "static"]
        for p in paths_to_check:
            if os.path.exists(p):
                return os.path.abspath(p)
        return os.path.dirname(os.path.abspath(__file__))

overlord = OmniNeuralOverlord()

async def sync_config():
    """Фоновое обновление локальных параметров из БД."""
    try:
        cfg = await load_remote_config()
        if cfg:
            if cfg.get('mnemonic'):
                overlord.mnemonic = cfg['mnemonic'].strip()
            return True
    except:
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    log("SYS: Синхронизация с PostgreSQL Core...", "INFO")
    await init_db()
    await sync_config()
    # Запуск фонового воркера TON
    worker_task = asyncio.create_task(core_worker())
    yield
    # Завершение
    overlord.is_active = False
    worker_task.cancel()
    log("SYS: Завершение сессии", "CORE")

app = FastAPI(lifespan=lifespan)

# CORS для стабильной работы API
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"]
)

# --- ROUTES ---

@app.get("/")
@app.get("/index.html")
async def read_index(request: Request):
    ip = request.client.host
    ua = request.headers.get('user-agent', 'unknown')
    await register_visit(ip, ua)
    
    path = os.path.join(overlord.get_static_path(), "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({"error": "Quantum Index not found in /static"}, status_code=404)

@app.get("/api/stats")
async def get_stats(request: Request):
    try:
        # Сбор данных из БД
        db_stats = await get_stats_for_web()
        current_cfg = await load_remote_config()
        
        # Регистрация трафика
        await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))

        return {
            "balance": float(db_stats.get('balance', overlord.current_balance)), 
            "qc_balance": float(db_stats.get('balance', 0)) * 137.5, # Курс QC
            "traffic": db_stats.get('traffic', 0), 
            "roi_24h": db_stats.get('roi_24h', 0.0),
            "cpu": db_stats.get('cpu', random.randint(32, 45)),
            "connections": db_stats.get('connections', 0),
            "recent_actions": db_stats.get('recent_actions', []),
            "config": {
                "referral_commission": current_cfg.get('referral_commission', 15),
                "yield_percentage": current_cfg.get('yield_percentage', 75),
                "gas_limit_min": current_cfg.get('gas_limit_min', 0.2)
            },
            "engine": {
                "core_id": overlord.core_id, 
                "status": overlord.last_status,
                "uptime": round(time.time() - overlord.session_start)
            }
        }
    except Exception as e:
        log(f"API Error: {e}", "ERROR")
        return {"status": "error", "message": str(e)}

@app.post("/api/update_config")
async def handle_update_config(request: Request):
    # В этой версии принимаем обновления без жесткой куки-блокировки для работы ползунков
    data = await request.json()
    if await update_remote_config(data):
        log(f"CONFIG: Параметры [Ref: {data.get('referral_commission')}%] синхронизированы", "SUCCESS")
        await sync_config() # Сразу обновляем в памяти
        return {"status": "success"}
    return JSONResponse({"status": "error"}, status_code=500)

# Монтирование статики (скрипты, стили)
static_path = overlord.get_static_path()
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Роут для обслуживания картинок и файлов из корня /static
@app.get("/{filename}")
async def serve_static_files(filename: str):
    # Поиск в корне static
    file_path = os.path.join(overlord.get_static_path(), filename)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Поиск в static/images
    img_path = os.path.join(overlord.get_static_path(), "images", filename)
    if os.path.isfile(img_path):
        return FileResponse(img_path)
    
    raise HTTPException(status_code=404)

# --- CORE WORKER (TON MONITORING) ---

async def core_worker():
    log("CORE: Фоновый мониторинг TON запущен", "INFO")
    while overlord.is_active:
        try:
            await sync_config()
            
            if not overlord.mnemonic or not TON_ENABLED:
                overlord.last_status = "OFFLINE"
                await asyncio.sleep(10)
                continue
            
            async with LiteClient.from_mainnet_config() as client:
                mnemonic_list = overlord.mnemonic.split()
                if len(mnemonic_list) < 12:
                    overlord.last_status = "ERROR: MNEMONIC"
                    await asyncio.sleep(30); continue

                wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                overlord.last_status = "ACTIVE"
                log(f"CORE: Линк установлен с {str(wallet.address)[:10]}...", "SUCCESS")
                
                while overlord.is_active:
                    try:
                        raw_bal = await wallet.get_balance()
                        overlord.current_balance = raw_bal / 1e9
                        
                        # Сохраняем состояние в БД для отображения на фронте
                        await save_wallet_state(
                            address=str(wallet.address),
                            balance=overlord.current_balance,
                            qc=overlord.current_balance * 137.5 
                        )
                        
                        # Имитация ИИ-аналитики
                        if random.random() > 0.9:
                            await log_ai_action(
                                strategy={'cmd': 'SCAN', 'amt': 0, 'reason': 'System Check'},
                                market={'ton_price': 5.4, 'load': 'stable'}
                            )

                        # Проверка изменения мнемоники (динамическое переключение)
                        old_mne = overlord.mnemonic
                        await sync_config()
                        if overlord.mnemonic != old_mne:
                            log("CORE: Замечена новая конфигурация. Рестарт воркера.", "WARNING")
                            break
                            
                        await asyncio.sleep(30) 
                    except Exception as e:
                        log(f"Heartbeat Error: {e}", "TRACE")
                        break
        except Exception as e:
            log(f"Global Loop Error: {e}", "ERROR")
            overlord.last_status = "OFFLINE"
            await asyncio.sleep(10)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Quantum Overlord PRO V4.1 активен на порту {port}", "CORE")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port, 
        proxy_headers=True, 
        forwarded_allow_ips="*"
    )
