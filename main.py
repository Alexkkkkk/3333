import asyncio
import os
import json
import time
import sys
import random
import hashlib
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

# Попытка импорта psutil (защита от ModuleNotFoundError на хостинге)
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Импорт функций из модуля database.py
from database import (
    init_db, get_stats_for_web, register_visit, 
    save_wallet_state, log_ai_action, update_remote_config, 
    load_remote_config
)

load_dotenv()

# --- ПАРАМЕТРЫ ПУЛА ---
STAKE_THRESHOLD = 5.0     # Порог для автоматизации (стейкаем если > 5 TON)
GAS_RESERVE = 1.0         # Минимум оставляем на газ
AUTO_STAKE_ENABLED = True # Флаг автоматизации

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
log(">>> ЗАПУСК ГИБРИДНОГО ЯДРА QUANTUM V4.1 + СОБСТВЕННЫЙ ПУЛ <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    log("L1: Библиотеки TON (pytoniq) загружены", "SUCCESS")
    TON_ENABLED = True
except ImportError:
    log("Критическая ошибка: pytoniq не найден! Режим эмуляции.", "ERROR")
    TON_ENABLED = False

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"QC-CORE-{os.urandom(2).hex().upper()}"
        self.mnemonic = None
        self.last_status = "INITIALIZING"
        self.current_balance = 0.0
        self.processed_txs = set() # Память обработанных транзакций

    def get_static_path(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        paths_to_check = [os.path.join(base_dir, "static"), "./static", "/app/static"]
        for p in paths_to_check:
            if os.path.exists(p): return os.path.abspath(p)
        static_p = os.path.join(base_dir, "static")
        os.makedirs(static_p, exist_ok=True)
        return static_p

overlord = OmniNeuralOverlord()
static_dir = overlord.get_static_path()

async def sync_config():
    try:
        cfg = await load_remote_config()
        if cfg and cfg.get('mnemonic'):
            overlord.mnemonic = cfg['mnemonic'].strip()
            return True
    except Exception as e:
        log(f"Sync Config Fail: {e}", "TRACE")
    return False

# --- ЛОГИКА СОБСТВЕННОГО ПУЛА ---
async def process_pool_inflow(wallet):
    """Анализ входящих транзакций в пул."""
    try:
        # В режиме эмуляции просто пропускаем
        if not TON_ENABLED: return

        # Получаем последние транзакции кошелька
        method_res = await wallet.client.get_transactions(wallet.address, limit=5)
        
        for tx in method_res:
            tx_hash = tx.hash.hex()
            if tx_hash in overlord.processed_txs: continue
            
            # Проверяем входящее сообщение
            if tx.in_msg and tx.in_msg.value > 0:
                amount = tx.in_msg.value / 1e9
                sender = tx.in_msg.source.to_str() if tx.in_msg.source else "UNKNOWN"
                
                log(f"POOL: Обнаружен депозит {amount} TON от {sender[:8]}...", "SUCCESS")
                
                # Записываем действие в лог ИИ
                await log_ai_action(
                    strategy={'cmd': 'DEPOSIT_DETECTED', 'from': sender, 'amount': amount},
                    market={'pool_status': 'active'}
                )
                
            overlord.processed_txs.add(tx_hash)
            
    except Exception as e:
        log(f"Pool Logic Error: {e}", "TRACE")

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log("SYS: Подключение к Quancore Nexus DB...", "INFO")
    try:
        await init_db()
        await sync_config()
        worker_task = asyncio.create_task(core_worker())
        log(f"SYS: Quantum Core Online ({overlord.core_id})", "SUCCESS")
        yield
    finally:
        overlord.is_active = False
        worker_task.cancel()
        log("SYS: Ядро деактивировано", "CORE")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"]
)

# --- API ROUTES ---

@app.get("/")
@app.get("/index.html")
async def read_index(request: Request):
    await register_visit(request.client.host, request.headers.get('user-agent', 'unknown'))
    path = os.path.join(static_dir, "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({"error": "Index not found"}, status_code=404)

@app.get("/api/stats")
async def get_stats(request: Request):
    try:
        db_stats = await get_stats_for_web() or {}
        current_cfg = await load_remote_config() or {}
        cpu_usage = psutil.cpu_percent() if PSUTIL_AVAILABLE else random.randint(14, 26)

        return {
            "balance": round(float(overlord.current_balance), 2), 
            "qc_balance": round(float(overlord.current_balance * 137.5), 2),
            "traffic": round(db_stats.get('traffic', random.uniform(42.0, 48.0)), 2), 
            "roi": db_stats.get('roi_24h', 4.2),
            "cpu": cpu_usage,
            "visitors": db_stats.get('traffic', 1),
            "engine": {
                "core_id": overlord.core_id, 
                "status": overlord.last_status,
                "uptime": round(time.time() - overlord.session_start)
            },
            "config": {
                "yield": current_cfg.get('yield_percentage', 75),
                "ref": current_cfg.get('referral_commission', 15)
            }
        }
    except Exception as e:
        log(f"API Error: {e}", "ERROR")
        return {"status": "offline", "balance": 0.0}

# --- РОУТИНГ СТАТИКИ ---
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/{path:path}")
async def serve_all_files(path: str):
    clean_path = path.strip("/")
    file_path = os.path.join(static_dir, clean_path)
    if os.path.isfile(file_path): return FileResponse(file_path)
    
    img_path = os.path.join(static_dir, "images", clean_path.split("/")[-1])
    if os.path.isfile(img_path): return FileResponse(img_path)

    html_path = os.path.join(static_dir, f"{clean_path}.html")
    if os.path.exists(html_path): return FileResponse(html_path)
    
    idx = os.path.join(static_dir, "index.html")
    return FileResponse(idx) if os.path.exists(idx) else JSONResponse({"error": "404"}, status_code=404)

# --- CORE WORKER ---

async def core_worker():
    log("CORE: Мониторинг пула запущен", "INFO")
    while overlord.is_active:
        try:
            await sync_config()
            if not overlord.mnemonic or not TON_ENABLED:
                overlord.last_status = "STANDBY"
                await asyncio.sleep(15)
                continue
            
            async with LiteClient.from_mainnet_config() as client:
                mnemonic_list = overlord.mnemonic.split()
                wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                overlord.last_status = "ACTIVE"
                
                while overlord.is_active:
                    try:
                        # 1. Проверяем баланс
                        raw_bal = await wallet.get_balance()
                        overlord.current_balance = raw_bal / 1e9
                        
                        # 2. Обработка входящих в Пул
                        await process_pool_inflow(wallet)
                        
                        # 3. Автоматизация стейкинга (логика решения)
                        if AUTO_STAKE_ENABLED and overlord.current_balance > STAKE_THRESHOLD:
                            stake_amount = overlord.current_balance - GAS_RESERVE
                            log(f"AUTO: Система готова направить {stake_amount:.2f} TON в Forge", "CORE")
                        
                        # Сохраняем состояние
                        await save_wallet_state(
                            address=str(wallet.address),
                            balance=overlord.current_balance,
                            qc=overlord.current_balance * 137.5 
                        )
                        
                        # Проверка смены мнемоники
                        old_mne = overlord.mnemonic
                        await sync_config()
                        if overlord.mnemonic != old_mne: break
                            
                        await asyncio.sleep(30) 
                    except Exception as e:
                        log(f"Worker Heartbeat Error: {e}", "TRACE")
                        break
        except Exception as e:
            log(f"Worker Loop Error: {e}", "ERROR")
            await asyncio.sleep(10)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")
