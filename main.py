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
        "CORE": "\033[95m"     # Magenta
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    print(f"{color}[{timestamp}] [{level}] {message}{reset}")

# --- УЛЬТРА-ЗАЩИЩЕННЫЙ ИМПОРТ ---
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    try:
        from pytoniq_core import BeginCell
    except ImportError:
        from pytoniq import BeginCell
    log("TON Dependencies: OK", "SUCCESS")
except ImportError:
    log("Critical: pytoniq not found! Ensure it is in requirements.txt", "ERROR")
    sys.exit(1)

try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("Database modules: OK", "SUCCESS")
except ImportError:
    log("database.py missing in root directory!", "ERROR")
    sys.exit(1)

load_dotenv()

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        self.pool_addr = None
        # Основной адрес хранилища
        self.vault_ton = Address("EQCt0-Ba6Y_9_6p20tH_E_Oq_H_O_O_O_O_O_O_O_O_O_O_O_O")
        self.mnemonic = None
        self.ai_key = None
        self.strategy_level = 10
        
        self.synaptic_history = []
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        log(f"Overlord initialized. Core ID: {self.core_id}", "CORE")

    async def update_config_from_db(self):
        """Синхронизация локальных переменных с базой данных Bothost."""
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                # Очистка строки от мусора
                self.mnemonic = cfg.get('mnemonic').strip().replace('\n', ' ').replace('\r', '')
                self.ai_key = cfg.get('ai_api_key', '').strip()
                
                pool_raw = cfg.get('dedust_pool')
                if pool_raw: 
                    self.pool_addr = Address(pool_raw)
                
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                self.last_status = "ACTIVE"
                return True
            return False
        except Exception as e:
            log(f"Config sync failure: {e}", "ERROR")
            return False

    # --- API & WEB ---
    async def handle_index(self, request):
        if os.path.exists('./static/index.html'):
            return web.FileResponse('./static/index.html')
        return web.Response(text="<h1 style='color:blue'>QUANTUM CORE ACTIVE</h1>", content_type='text/html')

    async def handle_get_stats(self, request):
        try:
            db_stats = await get_stats_for_web()
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
        try:
            data = await request.json()
            await update_remote_config(data)
            await self.update_config_from_db()
            log("Config updated via API Request", "SUCCESS")
            return web.json_response({"status": "success"})
        except Exception as e:
            return web.json_response({"status": "error", "msg": str(e)}, status=400)

    # --- ANALYTICS & NEURAL ---
    def _calculate_hyper_analytics(self):
        try:
            if len(self.synaptic_history) < 5: return None
            prices = np.array([h['price'] for h in self.synaptic_history if h['price'] > 0])
            if len(prices) < 5: return None
            
            diffs = np.abs(np.diff(prices))
            total_movement = np.sum(diffs)
            if total_movement == 0: return {"market_state": "STAGNANT", "fei": 0}
            fei = np.abs(prices[-1] - prices[0]) / total_movement
            return {"market_state": "TRENDING" if fei > 0.4 else "CHAOTIC", "fei": round(float(fei), 4)}
        except: return None

    async def fetch_neural_strategy(self, market_snapshot):
        if not self.ai_key: 
            return {"cmd": "WAIT", "reason": "No AI Key"}
        
        try:
            hyper = self._calculate_hyper_analytics()
            # Инициализация клиента для каждой сессии (рекомендуется для OpenAI v1+)
            client = openai.AsyncOpenAI(api_key=self.ai_key)
            
            res = await asyncio.wait_for(client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Analyze market. JSON ONLY: {\"cmd\": \"BUY\"/\"WAIT\", \"amt\": float, \"reason\": \"str\"}"},
                    {"role": "user", "content": json.dumps({"market": market_snapshot, "hyper": hyper})}
                ],
                response_format={ "type": "json_object" }
            ), timeout=15)
            
            return json.loads(res.choices[0].message.content)
        except Exception as e:
            log(f"Neural AI Error: {e}", "ERROR")
            return {"cmd": "WAIT", "reason": "AI Timeout/Error"}

    async def dispatch_hft_pulse(self, wallet, plan):
        if not self.pool_addr: return False
        try:
            amt = float(plan.get('amt', 0))
            if amt <= 0: return False
            
            nano_amt = int(amt * 1e9)
            
            # DeDust Swap Payload (0xea06185d - swap op)
            swap_payload = (BeginCell()
                            .store_uint(0xea06185d, 32) 
                            .store_uint(int(time.time() + 300), 64) 
                            .store_coins(nano_amt)
                            .store_address(self.pool_addr)
                            .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
            
            await wallet.transfer(destination=self.vault_ton, amount=nano_amt + int(0.2e9), body=swap_payload)
            self.total_ops += 1
            log(f"TON: Pulse successful. Op #{self.total_ops} | Amount: {amt}", "SUCCESS")
            return True
        except Exception as e:
            log(f"TON: Pulse failed: {e}", "ERROR")
            return False

    # --- RUNNERS ---
    async def start_web_server(self):
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_headers="*",
                allow_credentials=True,
                expose_headers="*",
                allow_methods="*"
            )
        })
        
        app.router.add_get('/', self.handle_index)
        app.router.add_get('/api/stats', self.handle_get_stats)
        app.router.add_post('/api/config', self.handle_update_config)
        
        if os.path.exists('static'):
            app.router.add_static('/static/', path='static', name='static')

        for route in list(app.router.routes()):
            cors.add(route)
        
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", 3000))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        log(f"Web Dashboard ONLINE (Port {port})", "SUCCESS")

    async def core_loop(self):
        log("Entering Core Loop...", "CORE")
        
        # Ожидание БД
        while True:
            try:
                await init_db()
                log("Database connected & tables initialized", "SUCCESS")
                break
            except Exception as e:
                log(f"DB connection waiting... ({e})", "WARNING")
                await asyncio.sleep(5)

        asyncio.create_task(self.start_web_server())

        while self.is_active:
            try:
                if not await self.update_config_from_db():
                    self.last_status = "WAITING_CONFIG"
                    log("Waiting for mnemonic/AI key in database...", "WARNING")
                    await asyncio.sleep(10)
                    continue

                client = LiteClient.from_mainnet_config()
                await client.start()
                
                try:
                    wallet = await WalletV4R2.from_mnemonic(client, self.mnemonic.split())
                    log(f"Wallet active: {wallet.address}", "SUCCESS")
                    
                    while self.is_active:
                        # Регулярная проверка обновлений конфига в БД
                        await self.update_config_from_db()
                        
                        market_state = await get_market_state()
                        p_curr = market_state['current_metrics']['price_ton']
                        self.synaptic_history.append({"price": p_curr, "time": time.time()})
                        if len(self.synaptic_history) > 500: self.synaptic_history.pop(0)

                        balance_nano = await wallet.get_balance()
                        balance = balance_nano / 1e9
                        log(f"Balance: {balance:.2f} TON | Price: {p_curr:.4f}", "INFO")

                        plan = await self.fetch_neural_strategy(market_state)
                        
                        if plan.get('cmd') == "BUY" and balance > (float(plan.get('amt', 0)) + 0.5):
                            if await self.dispatch_hft_pulse(wallet, plan):
                                await log_ai_action(plan, market_state['current_metrics'])
                        
                        await asyncio.sleep(20)

                finally:
                    await client.stop()

            except Exception as e:
                log(f"Core Error: {e}", "ERROR")
                traceback.print_exc()
                await asyncio.sleep(10)

if __name__ == "__main__":
    overlord = OmniNeuralOverlord()
    try:
        asyncio.run(overlord.core_loop())
    except KeyboardInterrupt:
        log("Shutdown requested", "WARNING")
    except Exception as fatal:
        log(f"Kernel Panic: {fatal}", "ERROR")
