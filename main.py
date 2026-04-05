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
        
        # Настройки входа (админ-панель)
        self.admin_login = "1"
        self.admin_pass = "1"
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
        log(f"Overlord initialized. Core ID: {self.core_id}", "CORE")

    def _clean_string(self, text):
        if not text: return ""
        return "".join(char for char in str(text) if ord(char) < 128).strip()

    def get_static_path(self):
        """Определяет путь к папке со статикой на сервере."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        check_paths = [
            os.path.join(base_dir, 'static'),
            os.path.join(os.getcwd(), 'static'),
            '/app/static'
        ]
        for p in check_paths:
            if os.path.exists(p):
                return p
        return None

    async def update_config_from_db(self):
        """Загружает настройки из PostgreSQL в память бота."""
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                raw_mnemonic = cfg.get('mnemonic', '')
                self.mnemonic = " ".join(raw_mnemonic.replace('\n', ' ').replace('\r', ' ').split())
                self.ai_key = self._clean_string(cfg.get('ai_api_key', ''))
                pool_raw = self._clean_string(cfg.get('dedust_pool', ''))
                if pool_raw: 
                    try: self.pool_addr = Address(pool_raw)
                    except: log(f"Ошибка формата адреса пула: {pool_raw}", "WARNING")
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                self.last_status = "ACTIVE"
                return True
            return False
        except Exception as e:
            log(f"Ошибка синхронизации конфига: {e}", "ERROR")
            return False

    def is_auth(self, request):
        return request.cookies.get("auth_token") == self.session_token

    # --- WEB HANDLERS ---

    async def handle_login(self, request):
        try:
            data = await request.json()
            if str(data.get("login")) == self.admin_login and str(data.get("password")) == self.admin_pass:
                res = web.json_response({"status": "success", "token": self.session_token})
                res.set_cookie("auth_token", self.session_token, max_age=86400, httponly=True)
                log("Успешный вход в админ-панель", "SUCCESS")
                return res
            return web.json_response({"status": "error", "msg": "Access Denied"}, status=401)
        except:
            return web.json_response({"status": "error"}, status=400)

    async def handle_index(self, request):
        """Раздает index.html из папки static/admin или static/."""
        static_dir = self.get_static_path()
        if not static_dir:
            return web.Response(text="Static directory not found", status=404)

        paths = [
            os.path.join(static_dir, 'admin', 'index.html'),
            os.path.join(static_dir, 'index.html')
        ]
        for path in paths:
            if os.path.exists(path):
                return web.FileResponse(path)
        
        return web.Response(text="index.html not found in static paths", status=404)

    async def handle_get_stats(self, request):
        if not self.is_auth(request):
            return web.json_response({"status": "unauthorized"}, status=401)
        try:
            db_stats = await get_stats_for_web()
            db_stats['balance'] = f"{self.current_balance:.2f}"
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
            log("Конфигурация обновлена через Web", "SUCCESS")
            return web.json_response({"status": "success"})
        except Exception as e:
            return web.json_response({"status": "error", "msg": str(e)}, status=400)

    # --- CORE ENGINE ---

    async def fetch_neural_strategy(self, market_snapshot):
        if not self.ai_key: return {"cmd": "WAIT", "reason": "No AI Key"}
        try:
            client = openai.AsyncOpenAI(api_key=self.ai_key)
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
            log(f"Ошибка нейросети: {e}", "ERROR")
            return {"cmd": "WAIT", "reason": "AI Error"}

    async def dispatch_hft_pulse(self, wallet, plan):
        if not self.pool_addr: return False
        try:
            amt = float(plan.get('amt', 0))
            if amt <= 0: return False
            nano_amt = int(amt * 1e9)
            
            # Тело транзакции для свопа (DeDust/Ston.fi style)
            swap_payload = (BeginCell()
                            .store_uint(0xea06185d, 32) 
                            .store_uint(int(time.time() + 300), 64) 
                            .store_coins(nano_amt)
                            .store_address(self.pool_addr)
                            .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
            
            await wallet.transfer(destination=self.vault_ton, amount=nano_amt + int(0.2e9), body=swap_payload)
            self.total_ops += 1
            log(f"Импульс отправлен: {amt} TON", "SUCCESS")
            return True
        except Exception as e:
            log(f"TON: Ошибка импульса: {e}", "ERROR")
            return False

    async def start_web_server(self):
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_headers="*", allow_methods="*", allow_credentials=True
            )
        })
        
        # Маршруты
        app.router.add_get('/', self.handle_index)
        app.router.add_get('/amin', self.handle_index)
        app.router.add_post('/api/login', self.handle_login)
        app.router.add_get('/api/stats', self.handle_get_stats)
        app.router.add_post('/api/config', self.handle_update_config)
        
        static_dir = self.get_static_path()
        if static_dir:
            app.router.add_static('/static/', path=static_dir, name='static')
            log(f"Статика подключена: {static_dir}", "SUCCESS")
        
        for route in list(app.router.routes()): cors.add(route)
        
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", 3000))
        await web.TCPSite(runner, '0.0.0.0', port).start()
        log(f"ADMIN PANEL: https://quantum.bothost.tech/amin", "SUCCESS")

    async def core_loop(self):
        # 1. Сначала БД
        while True:
            try:
                await init_db()
                log("Соединение с БД установлено", "SUCCESS")
                break
            except: 
                log("Ожидание базы данных...", "WARNING")
                await asyncio.sleep(5)

        # 2. Запуск веб-сервера
        asyncio.create_task(self.start_web_server())

        # 3. Основной цикл TON
        while self.is_active:
            try:
                if not await self.update_config_from_db():
                    log("Ожидание конфига в БД...", "WARNING")
                    await asyncio.sleep(10); continue

                async with LiteClient.from_mainnet_config() as client:
                    mnemonic_list = self.mnemonic.split()
                    if len(mnemonic_list) < 12:
                        log("Мнемоника в БД невалидна!", "ERROR")
                        await asyncio.sleep(30); continue

                    wallet = await WalletV4R2.from_mnemonic(client, mnemonic_list)
                    log(f"Ядро подключено к кошельку: {wallet.address}", "SUCCESS")
                    
                    while self.is_active:
                        try:
                            await client.reconnect()
                            await self.update_config_from_db()
                            market_state = await get_market_state()
                            
                            try:
                                balance_nano = await asyncio.wait_for(wallet.get_balance(), timeout=12.0)
                                self.current_balance = balance_nano / 1e9
                            except:
                                log("TON Node Timeout: Смена сервера...", "WARNING")
                                break

                            plan = await self.fetch_neural_strategy(market_state)
                            if plan.get('cmd') == "BUY" and self.current_balance > (float(plan.get('amt', 0)) + 0.5):
                                if await self.dispatch_hft_pulse(wallet, plan):
                                    await log_ai_action(plan, market_state.get('current_metrics', {}))
                            
                            await asyncio.sleep(20)
                        except Exception as inner_e:
                            if any(msg in str(inner_e) for msg in ["-400", "Connect call failed"]):
                                break
                            log(f"Ошибка итерации: {inner_e}", "TRACE")
                            await asyncio.sleep(10)
            
            except Exception as e:
                log(f"Критический сбой ядра: {e}", "ERROR")
                await asyncio.sleep(10)

if __name__ == "__main__":
    overlord = OmniNeuralOverlord()
    try:
        asyncio.run(overlord.core_loop())
    except KeyboardInterrupt:
        log("Система остановлена пользователем", "WARNING")
    except Exception as e:
        log(f"FATAL EXCEPTION:\n{traceback.format_exc()}", "ERROR")
