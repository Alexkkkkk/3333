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
from dotenv import load_dotenv
from aiohttp import web
import aiohttp_cors

# --- СИСТЕМА ЛОГИРОВАНИЯ ---
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {
        "INFO": "\033[94m",    # Blue
        "SUCCESS": "\033[92m", # Green
        "WARNING": "\033[93m", # Yellow
        "ERROR": "\033[91m",    # Red
        "CORE": "\033[95m",    # Magenta
        "TRACE": "\033[90m"     # Grey
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    print(f"{color}[{timestamp}] [{level}] {message}{reset}", flush=True)

# --- УЛЬТРА-ЗАЩИЩЕННЫЙ ИМПОРТ ---
log(">>> ИНИЦИАЛИЗАЦИЯ ЯДРА QUANTUM <<<", "CORE")
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    try:
        from pytoniq import begin_cell as BeginCell
        log("TON: Используется метод begin_cell", "SUCCESS")
    except ImportError:
        try:
            from pytoniq_core import BeginCell
        except ImportError:
            from pytoniq import BeginCell
    log("Зависимости TON: OK", "SUCCESS")
except ImportError:
    log("Критическая ошибка: pytoniq не найден!", "ERROR")
    sys.exit(1)

try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("Модули базы данных: OK", "SUCCESS")
except ImportError:
    log("Файл database.py не найден!", "ERROR")
    sys.exit(1)

load_dotenv()

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        # Настройки входа
        self.admin_login = "1"
        self.admin_pass = "1"
        self.session_token = os.urandom(32).hex() 
        
        self.pool_addr = None
        self.vault_ton = Address("UQBo0iou1BlB_8Xg0Hn_rUeIcrpyyhoboIauvnii889OFRoI")
        
        self.mnemonic = None
        self.ai_key = None
        self.strategy_level = 10
        
        # Данные пула для отображения
        self.pool_reserves = {"ton": "0.00", "token": "0.00"}
        
        self.synaptic_history = []
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        self.current_balance = 0.0
        log(f"Overlord initialized. Core ID: {self.core_id}", "CORE")

    def _clean_string(self, text):
        if not text: return ""
        return "".join(char for char in str(text) if ord(char) < 128).strip()

    async def update_config_from_db(self):
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                self.mnemonic = self._clean_string(cfg.get('mnemonic')).replace('\n', ' ').replace('\r', '')
                self.ai_key = self._clean_string(cfg.get('ai_api_key', ''))
                pool_raw = self._clean_string(cfg.get('dedust_pool'))
                if pool_raw: 
                    try: 
                        self.pool_addr = Address(pool_raw)
                    except: 
                        log("Ошибка формата адреса пула", "WARNING")
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                self.last_status = "ACTIVE"
                return True
            return False
        except Exception as e:
            log(f"Ошибка синхронизации конфига: {e}", "ERROR")
            return False

    # --- СИСТЕМА АВТОРИЗАЦИИ ---
    def is_auth(self, request):
        return request.cookies.get("auth_token") == self.session_token

    async def handle_login(self, request):
        try:
            data = await request.json()
            if data.get("login") == self.admin_login and data.get("password") == self.admin_pass:
                res = web.json_response({"status": "success"})
                res.set_cookie("auth_token", self.session_token, max_age=86400, httponly=True)
                log("Успешный вход в админ-панель", "SUCCESS")
                return res
            return web.json_response({"status": "error", "msg": "Access Denied"}, status=401)
        except:
            return web.json_response({"status": "error"}, status=400)

    # --- API & WEB ---
    async def handle_index(self, request):
        if os.path.exists('./static/index.html'):
            return web.FileResponse('./static/index.html')
        return web.Response(text="<h1>QUANTUM CORE ACTIVE</h1>", content_type='text/html')

    async def handle_get_stats(self, request):
        if not self.is_auth(request):
            return web.json_response({"status": "unauthorized"}, status=401)
        try:
            db_stats = await get_stats_for_web()
            db_stats['balance'] = f"{self.current_balance:.2f}"
            
            # Добавляем блок информации о пуле
            db_stats['pool_info'] = {
                "address": str(self.pool_addr) if self.pool_addr else "NOT CONFIGURED",
                "reserve_ton": self.pool_reserves["ton"],
                "reserve_token": self.pool_reserves["token"],
                "status": "SYNCED" if self.pool_addr else "WAITING"
            }
            
            db_stats['engine'] = {
                "core_id": self.core_id,
                "ops_total": self.total_ops,
                "uptime": round(time.time() - self.session_start),
                "last_status": self.last_status
            }
            return web.json_response(db_stats)
        except Exception as e:
            return web.json_response({"status": "error", "msg": str(e)})

    async def handle_update_config(self, request):
        if not self.is_auth(request):
            return web.json_response({"status": "unauthorized"}, status=401)
        try:
            data = await request.json()
            await update_remote_config(data)
            await self.update_config_from_db()
            log("Конфигурация обновлена через Web-интерфейс", "SUCCESS")
            return web.json_response({"status": "success"})
        except Exception as e:
            return web.json_response({"status": "error", "msg": str(e)}, status=400)

    # --- ANALYTICS & NEURAL ---
    async def fetch_neural_strategy(self, market_snapshot):
        if not self.ai_key: return {"cmd": "WAIT", "reason": "No AI Key"}
        try:
            openai.api_key = self.ai_key
            res = await asyncio.wait_for(openai.ChatCompletion.acreate(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Analyze market. JSON ONLY: {\"cmd\": \"BUY\"/\"WAIT\", \"amt\": float, \"reason\": \"str\"}"},
                    {"role": "user", "content": json.dumps({"market": market_snapshot})}
                ]
            ), timeout=15)
            return json.loads(res.choices[0].message.content)
        except Exception as e:
            log(f"Ошибка нейросети: {e}", "ERROR")
            return {"cmd": "WAIT", "reason": "AI Error"}

    async def dispatch_hft_pulse(self, wallet, plan):
        if not self.pool_addr: return False
        try:
            amt = float(plan.get('amt', 0))
            nano_amt = int(amt * 1e9)
            swap_payload = (BeginCell()
                            .store_uint(0xea06185d, 32) 
                            .store_uint(int(time.time() + 300), 64) 
                            .store_coins(nano_amt)
                            .store_address(self.pool_addr)
                            .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
            
            await wallet.transfer(destination=self.vault_ton, amount=nano_amt + int(0.2e9), body=swap_payload)
            self.total_ops += 1
            return True
        except Exception as e:
            log(f"TON: Ошибка импульса: {e}", "ERROR")
            return False

    async def start_web_server(self):
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_headers="*", allow_methods="*")})
        
        app.router.add_get('/', self.handle_index)
        app.router.add_post('/api/login', self.handle_login)
        app.router.add_get('/api/stats', self.handle_get_stats)
        app.router.add_post('/api/config', self.handle_update_config)
        
        if os.path.exists('static'):
            app.router.add_static('/static/', path='static', name='static')
        
        for route in list(app.router.routes()): cors.add(route)
        
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", 3000))
        await web.TCPSite(runner, '0.0.0.0', port).start()
        log(f"Secure Admin Panel ONLINE (Port {port})", "SUCCESS")

    async def core_loop(self):
        while True:
            try:
                await init_db()
                break
            except: await asyncio.sleep(5)

        asyncio.create_task(self.start_web_server())

        while self.is_active:
            try:
                if not await self.update_config_from_db():
                    log("Ожидание конфига в БД...", "WARNING")
                    await asyncio.sleep(10); continue

                async with LiteClient.from_mainnet_config() as client:
                    mnemonic_list = self.mnemonic.split()
                    if len(mnemonic_list) < 12:
                        await asyncio.sleep(30); continue

                    wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                    
                    while self.is_active:
                        await self.update_config_from_db()
                        market_state = await get_market_state()
                        self.current_balance = (await wallet.get_balance()) / 1e9
                        
                        # (Опционально) Здесь можно добавить логику запроса резервов пула 
                        # через client.run_get_method(self.pool_addr, 'get_reserves')
                        
                        plan = await self.fetch_neural_strategy(market_state)
                        if plan.get('cmd') == "BUY" and self.current_balance > (float(plan.get('amt', 0)) + 0.5):
                            if await self.dispatch_hft_pulse(wallet, plan):
                                await log_ai_action(plan, market_state['current_metrics'])
                        
                        await asyncio.sleep(20)
            except Exception as e:
                log(f"Ошибка ядра: {e}", "ERROR")
                await asyncio.sleep(10)

if __name__ == "__main__":
    overlord = OmniNeuralOverlord()
    try:
        asyncio.run(overlord.core_loop())
    except KeyboardInterrupt:
        log("Shutdown", "WARNING")
