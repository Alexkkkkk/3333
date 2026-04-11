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
        # Проверяем стандартные пути для Bothost и Docker
        check_paths = [
            os.path.join(base_dir, 'static'),
            os.path.join(base_dir, '..', 'static'),
            '/app/static',
            'static'
        ]
        for p in check_paths:
            if os.path.exists(p) and os.path.isdir(p):
                return p
        return "static"

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

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- WEB & API ROUTES ---

@app.get("/")
@app.get("/index.html")
async def serve_index():
    path = os.path.join(overlord.get_static_path(), "index.html")
    return FileResponse(path) if os.path.exists(path) else JSONResponse({"error": "No index"}, 404)

# Фикс для манифеста (TON Connect часто ищет его в корне)
@app.get("/tonconnect-manifest.json")
async def serve_manifest():
    path = os.path.join(overlord.get_static_path(), "tonconnect-manifest.json")
    return FileResponse(path) if os.path.exists(path) else JSONResponse({"error": "No manifest"}, 404)

# Фикс для картинок, если они запрашиваются как /images/...
@app.get("/images/{file_name}")
async def serve_images(file_name: str):
    path = os.path.join(overlord.get_static_path(), "images", file_name)
    return FileResponse(path) if os.path.exists(path) else Response(status_code=404)

@app.get("/admin")
@app.get("/admin.html")
async def serve_admin():
    # Пробуем найти админку и в корне static, и в static/admin/
    paths = [
        os.path.join(overlord.get_static_path(), "admin.html"),
        os.path.join(overlord.get_static_path(), "admin", "admin.html")
    ]
    for p in paths:
        if os.path.exists(p):
            return FileResponse(p, headers={"Cache-Control": "no-store"})
    return JSONResponse({"error": "Admin panel not found"}, 404)

@app.get("/api/stats")
async def get_stats():
    try:
        db_stats = await get_stats_for_web() if DB_ENABLED else {}
        metrics = {
            'balance': f"{overlord.current_balance:.2f}",
            'traffic': round(random.uniform(400, 800), 2),
            'ping': random.randint(15, 45), # Добавили пинг для радара
            'cpu': random.randint(20, 45),
            'ram': random.randint(60, 85),
            'connections': random.randint(5, 12),
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

# --- CORE WORKER ---
async def core_worker():
    if DB_ENABLED:
        while True:
            try:
                await init_db()
                log("DB: Подключено", "SUCCESS")
                break
            except: await asyncio.sleep(5)

    while overlord.is_active:
        try:
            # Здесь будет твоя логика синхронизации с TON (как в твоем исходнике)
            # Для примера ставим статус ACTIVE
            overlord.last_status = "ACTIVE"
            await asyncio.sleep(60)
        except Exception as e:
            log(f"Core Loop Error: {e}", "ERROR")
            await asyncio.sleep(10)

# Монтируем статику (Важно: делать это в самом конце)
static_p = overlord.get_static_path()
if os.path.exists(static_p):
    app.mount("/static", StaticFiles(directory=static_p), name="static")
    log(f"STATIC: Папка {static_p} примонтирована", "INFO")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    log(f"SYSTEM: Quantum Overlord V3.5 запущен на порту {port}", "CORE")
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")
