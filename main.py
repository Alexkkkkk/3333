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
from aiohttp import web
import aiohttp_cors

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

# --- ПРОВЕРКА ОКРУЖЕНИЯ ---
log(">>> ЗАПУСК СИСТЕМЫ NEURAL SENTINEL V3 <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    from pytoniq import begin_cell as BeginCell
    log("Библиотеки TON загружены успешно", "SUCCESS")
except ImportError as e:
    log(f"Ошибка импорта pytoniq: {e}", "ERROR")
    sys.exit(1)

try:
    # Загружаем функции из твоего файла database.py
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("Модули базы данных подключены", "SUCCESS")
except ImportError as e:
    log(f"Ошибка импорта database.py: {e}", "ERROR")
    sys.exit(1)

load_dotenv()

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"SENTINEL-{os.urandom(2).hex().upper()}"
        
        # Настройки доступа
        self.admin_login = os.getenv("ADMIN_LOGIN", "1")
        self.admin_pass = os.getenv("ADMIN_PASS", "1")
        self.session_token = os.urandom(16).hex() 
        
        # Переменные состояния
        self.mnemonic = None
        self.ai_key = None
        self.target_pool = None
        self.strategy_level = 10
        self.current_balance = 0.0
        self.total_ops = 0
        self.last_status = "BOOTING"
        self.runner = None
        
        log(f"Ядро {self.core_id} готово к работе", "CORE")

    def get_static_path(self):
        base = os.path.dirname(os.path.abspath(__file__))
        static_path = os.path.join(base, 'static')
        return static_path if os.path.exists(static_path) else None

    # --- WEB HANDLERS ---
    async def handle_index(self, request):
        path = request.path.lower().strip('/')
        static_dir = self.get_static_path()
        if not static_dir: return web.Response(text="Static folder not found", status=404)

        # Логика поиска admin.html внутри static/admin/
        if path == '' or path == 'index.html':
            target = os.path.join(static_dir, 'index.html')
        elif path == 'admin' or path == 'admin/admin.html':
            target = os.path.join(static_dir, 'admin', 'admin.html')
        else:
            target = os.path.join(static_dir, path)

        if os.path.exists(target) and not os.path.isdir(target):
            return web.FileResponse(target)
        return web.FileResponse(os.path.join(static_dir, 'index.html'))

    async def handle_login(self, request):
        try:
            data = await request.json()
            if str(data.get("login")) == self.admin_login and str(data.get("password")) == self.admin_pass:
                res = web.json_response({"status": "success", "token": self.session_token})
                # Устанавливаем куку (httponly=False чтобы JS мог проверить её наличие)
                res.set_cookie("auth_token", self.session_token, httponly=False)
                log(f"AUTH: Вход в терминал [{request.remote}]", "SUCCESS")
                return res
            return web.json_response({"status": "error"}, status=401)
        except: return web.json_response({"status": "error"}, status=400)

    async def handle_save_config(self, request):
        """Сохранение конфига из CORE_PROTOCOL_SETTINGS твоего HTML"""
        if request.cookies.get("auth_token") != self.session_token:
            return web.json_response({"status": "unauthorized"}, status=401)
        
        try:
            data = await request.json()
            # Обновляем в БД
            await update_remote_config(data)
            
            # Обновляем в памяти объекта
            self.mnemonic = data.get('mnemonic', self.mnemonic)
            self.ai_key = data.get('ai_api_key', self.ai_key)
            self.target_pool = data.get('dedust_pool', self.target_pool)
            self.strategy_level = data.get('ai_strategy_level', self.strategy_level)
            
            log(f"CONFIG: База данных и ядро обновлены. Стратегия: {self.strategy_level}", "SUCCESS")
            return web.json_response({"status": "success"})
        except Exception as e:
            log(f"CONFIG: Ошибка: {e}", "ERROR")
            return web.json_response({"status": "error"}, status=500)

    async def handle_get_stats(self, request):
        """Отдает данные для всех виджетов admin.html"""
        if request.cookies.get("auth_token") != self.session_token:
            return web.json_response({"status": "unauthorized"}, status=401)
        
        db_stats = await get_stats_for_web()
        
        # Формируем JSON точно под твой JavaScript в admin.html
        response_data = {
            "balance": f"{self.current_balance:.2f}",
            "engine": {
                "core_id": self.core_id,
                "last_status": self.last_status,
                "ops_total": self.total_ops
            },
            "pool_info": {
                "address": self.target_pool if self.target_pool else "NOT CONFIGURED",
                "reserve_ton": db_stats.get("reserve_ton", "0.00"),
                "reserve_token": db_stats.get("reserve_token", "0.00"),
                "status": "STABLE" if self.is_active else "HALTED"
            },
            "current_metrics": db_stats.get("current_metrics", {"price_ton": "0.00"})
        }
        return web.json_response(response_data)

    async def handle_connect_wallet(self, request):
        try:
            data = await request.json()
            log(f"WEB: Подключен клиентский кошелек: {data.get('address')}", "INFO")
            return web.json_response({"status": "ok", "synced": True})
        except: return web.json_response({"status": "error"}, status=400)

    async def start_web_server(self):
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")
        })
        
        app.router.add_get('/', self.handle_index)
        app.router.add_get('/admin', self.handle_index)
        app.router.add_post('/api/login', self.handle_login)
        app.router.add_get('/api/stats', self.handle_get_stats)
        app.router.add_post('/api/config', self.handle_save_config)
        app.router.add_post('/api/connect', self.handle_connect_wallet)
        
        static_dir = self.get_static_path()
        if static_dir:
            app.router.add_static('/static/', path=static_dir)
            if os.path.exists(os.path.join(static_dir, 'images')):
                app.router.add_static('/images/', path=os.path.join(static_dir, 'images'))

        for route in list(app.router.routes()): cors.add(route)
        
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        port = int(os.getenv("PORT", 3000))
        await web.TCPSite(self.runner, '0.0.0.0', port).start()
        log(f"СЕРВЕР: Терминал запущен на порту {port}", "SUCCESS")

    async def fetch_neural_strategy(self, market_snapshot):
        if not self.ai_key:
            return {"cmd": "WAIT", "reason": "No API Key"}
        try:
            client = openai.AsyncOpenAI(api_key=self.ai_key)
            res = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": f"Strategy Intensity: {self.strategy_level}. Output JSON ONLY."},
                          {"role": "user", "content": json.dumps(market_snapshot)}],
                response_format={"type": "json_object"}, timeout=12
            )
            return json.loads(res.choices[0].message.content)
        except Exception as e:
            log(f"AI: Ошибка инференса: {e}", "ERROR")
            return {"cmd": "WAIT", "reason": "AI_OFFLINE"}

    async def core_loop(self):
        log("БАЗА: Инициализация протоколов...", "INFO")
        while True:
            try:
                await init_db()
                log("БАЗА: Соединение установлено", "SUCCESS")
                break
            except:
                log("БАЗА: Ожидание PostgreSQL...", "WARNING")
                await asyncio.sleep(5)

        asyncio.create_task(self.start_web_server())

        while self.is_active:
            try:
                # Загружаем актуальный конфиг из БД
                cfg = await load_remote_config()
                if cfg:
                    self.mnemonic = cfg.get('mnemonic', self.mnemonic)
                    self.ai_key = cfg.get('ai_api_key', self.ai_key)
                    self.target_pool = cfg.get('dedust_pool', self.target_pool)
                    self.strategy_level = cfg.get('ai_strategy_level', self.strategy_level)
                
                if not self.mnemonic:
                    self.last_status = "WAITING_CONFIG"
                    await asyncio.sleep(10); continue

                async with LiteClient.from_mainnet_config() as client:
                    wallet = await WalletV4R2.from_mnemonic(client, self.mnemonic.split())
                    self.last_status = "ACTIVE"
                    log(f"TON: Узел {wallet.address} синхронизирован", "SUCCESS")
                    
                    while self.is_active:
                        try:
                            balance_nano = await asyncio.wait_for(wallet.get_balance(), timeout=10.0)
                            self.current_balance = balance_nano / 1e9
                            
                            market = await get_market_state()
                            plan = await self.fetch_neural_strategy(market)
                            
                            if plan.get('cmd') == "BUY":
                                log(f"AI_OPS: Исполнение команды КУПИТЬ", "SUCCESS")
                                await self.dispatch_hft_pulse(wallet, plan)
                            
                            await asyncio.sleep(20)
                        except Exception as e:
                            log(f"LOOP: Перезапуск цикла: {e}", "ERROR")
                            await asyncio.sleep(5); break

            except Exception as e:
                log(f"CRITICAL: Сбой в ядре: {e}", "ERROR")
                self.last_status = "RECOVERY"
                await asyncio.sleep(10)

    async def dispatch_hft_pulse(self, wallet, plan):
        """Здесь будет логика транзакции в блокчейн"""
        self.total_ops += 1
        return True

if __name__ == "__main__":
    overlord = OmniNeuralOverlord()
    loop = asyncio.get_event_loop()
    
    async def shutdown(ol):
        log("СИСТЕМА: Деактивация...", "WARNING")
        ol.is_active = False
        if ol.runner: await ol.runner.cleanup()
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(overlord)))

    try:
        loop.run_until_complete(overlord.core_loop())
    except KeyboardInterrupt: pass
