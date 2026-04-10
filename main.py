import asyncio
import os
import json
import time
import sys
import random
import uvicorn
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# FastAPI компоненты
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# --- ИМПОРТ МОДУЛЕЙ ПРОЕКТА ---
try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    DB_ENABLED = True
except ImportError:
    DB_ENABLED = False

try:
    from pytoniq import LiteClient, WalletV4R2, Address
    TON_ENABLED = True
except ImportError:
    TON_ENABLED = False

load_dotenv()

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
    log_msg = f"[{timestamp}] [{level}] {message}"
    print(f"{colors.get(level, reset)}{log_msg}{reset}", flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")
    except: pass

# --- УПРАВЛЕНИЕ ЯДРОМ ---
class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        self.admin_login = os.getenv("ADMIN_LOGIN", "1")
        self.admin_pass = os.getenv("ADMIN_PASS", "1")
        self.session_token = os.urandom(32).hex() 
        
        self.mnemonic = None
        self.ai_key = None
        self.strategy_level = 10
        self.pool_addr = None
        
        self.last_status = "INITIALIZING"
        self.current_balance = 0.0

    def get_static_path(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        check_paths = [os.path.join(base_dir, 'static'), '/app/static', 'static']
        for p in check_paths:
            if os.path.exists(p): return p
        return "static"

    async def sync_config(self):
        """Полная синхронизация параметров с БД."""
        if not DB_ENABLED: return False
        try:
            cfg = await load_remote_config()
            if cfg:
                # Очистка и сохранение мнемоники
                raw_mne = str(cfg.get('mnemonic', '')).replace('\n', ' ').strip()
                self.mnemonic = " ".join(raw_mne.split())
                self.ai_key = str(cfg.get('ai_api_key', '')).strip()
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                
                pool_raw = str(cfg.get('dedust_pool', '')).strip()
                if pool_raw and pool_raw != "None":
                    try: self.pool_addr = Address(pool_raw)
                    except: pass
                return True
            return False
        except Exception as e:
            log(f"Sync Error: {e}", "ERROR")
            return False

overlord = OmniNeuralOverlord()

# --- LIFESPAN MANAGEMENT ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log(f">>> ЗАПУСК ЯДРА {overlord.core_id} <<<", "CORE")
    worker_task = asyncio.create_task(core_worker())
    yield
    overlord.is_active = False
    worker_task.cancel()
    log(">>> СИСТЕМА ОСТАНОВЛЕНА <<<", "CORE")

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- WEB & API ROUTES ---

@app.get("/")
@app.get("/index.html")
async def serve_index():
    path = os.path.join(overlord.get_static_path(), "index.html")
    return FileResponse(path) if os.path.exists(path) else JSONResponse({"error": "No index"}, 404)

@app.get("/admin")
async def serve_admin():
    path = os.path.join(overlord.get_static_path(), "admin.html")
    return FileResponse(path, headers={"Cache-Control": "no-store"}) if os.path.exists(path) else JSONResponse({"error": "No admin"}, 404)

@app.get("/api/stats")
async def get_stats():
    try:
        db_stats = await get_stats_for_web() if DB_ENABLED else {}
        metrics = {
            'balance': f"{overlord.current_balance:.2f}",
            'traffic': round(random.uniform(400, 800), 2),
            'cpu': random.randint(20, 45),
            'ram': random.randint(60, 85),
            'engine': {
                "core_id": overlord.core_id,
                "uptime": round(time.time() - overlord.session_start),
                "status": overlord.last_status
            }
        }
        metrics.update(db_stats)
        return metrics
    except: return {"status": "error"}

@app.post("/api/login")
async def handle_login(request: Request):
    data = await request.json()
    if str(data.get("login")) == overlord.admin_login and str(data.get("password")) == overlord.admin_pass:
        overlord.session_token = os.urandom(32).hex()
        res = JSONResponse({"status": "success"})
        res.set_cookie(key="auth_token", value=overlord.session_token, httponly=True, samesite="lax")
        return res
    return JSONResponse({"status": "error"}, status_code=401)

# --- CORE WORKER (Reality Synchronization) ---
async def core_worker():
    # 1. Ждем БД
    while DB_ENABLED:
        try:
            await init_db()
            log("DB: Подключено", "SUCCESS")
            break
        except: await asyncio.sleep(5)

    # 2. Главный цикл
    while overlord.is_active:
        try:
            await overlord.sync_config()
            
            if not overlord.mnemonic or not TON_ENABLED:
                overlord.last_status = "WAITING_CONFIG"
                await asyncio.sleep(10)
                continue

            async with LiteClient.from_mainnet_config() as client:
                mnemonic_list = overlord.mnemonic.split()
                if len(mnemonic_list) < 12:
                    overlord.last_status = "BAD_MNEMONIC"
                    await asyncio.sleep(20); continue

                wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                overlord.last_status = "ACTIVE"
                log(f"CORE READY: {wallet.address}", "SUCCESS")
                
                # Цикл мониторинга с проверкой "Reality Swap"
                while overlord.is_active:
                    try:
                        overlord.current_balance = (await wallet.get_balance()) / 1e9
                        
                        # Каждые 30 секунд проверяем, не изменилась ли мнемоника в БД
                        await asyncio.sleep(30)
                        old_mne = overlord.mnemonic
                        await overlord.sync_config()
                        
                        if overlord.mnemonic != old_mne:
                            log("REALITY SWAP: Обнаружена новая мнемоника, перезагрузка кошелька...", "WARNING")
                            break # Выход для реинициализации LiteClient
                            
                    except Exception as e:
                        log(f"Heartbeat Error: {e}", "TRACE")
                        break
        except Exception as e:
            log(f"Core Loop Error: {e}", "ERROR")
            await asyncio.sleep(10)

# Монтируем статику в конце
static_p = overlord.get_static_path()
if os.path.exists(static_p):
    app.mount("/static", StaticFiles(directory=static_p), name="static")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Quantum Overlord V3.5 запущен на порту {port}", "CORE")
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")
