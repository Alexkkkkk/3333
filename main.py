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
        "ERROR": "\033[91m",   # Red
        "CORE": "\033[95m"     # Magenta
    }
    reset = "\033[0m"
    color = colors.get(level, reset)
    print(f"{color}[{timestamp}] [{level}] {message}{reset}")

# --- УЛЬТРА-ЗАЩИЩЕННЫЙ ИМПОРТ ---
def check_dependencies():
    try:
        from pytoniq import LiteClient, WalletV4R2, Address
        from pytoniq.core import BeginCell
        log("Dependencies check: OK", "SUCCESS")
        return True
    except ImportError:
        log("pytoniq not found. Attempting auto-fix...", "WARNING")
        os.system(f"{sys.executable} -m pip install pytoniq")
        return False

if not check_dependencies():
    log("Restarting process after dependency install...", "CORE")
    os.execv(sys.executable, ['python'] + sys.argv)

from pytoniq import LiteClient, WalletV4R2, Address
try:
    from pytoniq.core import BeginCell
except:
    from pytoniq import BeginCell

# Модули БД
try:
    from database import (init_db, log_ai_action, get_market_state, 
                          get_stats_for_web, load_remote_config, update_remote_config)
    log("Database modules loaded successfully", "SUCCESS")
except ImportError:
    log("database.py missing in root! Critical failure.", "ERROR")
    sys.exit(1)

load_dotenv()

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        self.pool_addr = None
        self.vault_ton = Address("EQCt0-Ba6Y_9_6p20tH_E_Oq_H_O_O_O_O_O_O_O_O_O_O_O_O")
        self.mnemonic = None
        self.ai_key = None
        self.strategy_level = 10
        
        self.synaptic_history = []
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        log(f"Overlord initialized. Core ID: {self.core_id}", "CORE")

    async def update_config_from_db(self):
        log("Syncing configuration from database...", "INFO")
        try:
            cfg = await load_remote_config()
            if cfg and cfg.get('mnemonic'):
                self.mnemonic = cfg.get('mnemonic')
                self.ai_key = cfg.get('ai_api_key')
                openai.api_key = self.ai_key
                
                pool_raw = cfg.get('dedust_pool')
                if pool_raw: self.pool_addr = Address(pool_raw)
                
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                self.last_status = "ACTIVE"
                log("Configuration updated successfully", "SUCCESS")
                return True
            log("Configuration incomplete in DB (missing mnemonic)", "WARNING")
            return False
        except Exception as e:
            log(f"Config sync failure: {e}", "ERROR")
            return False

    # --- API & WEB ---
    async def handle_index(self, request):
        log(f"Web: Request to index from {request.remote}", "INFO")
        if os.path.exists('./static/index.html'):
            return web.FileResponse('./static/index.html')
        return web.Response(text="<h1>CORE ACTIVE</h1>", content_type='text/html')

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
            log(f"Web: Stats error: {e}", "ERROR")
            return web.json_response({"status": "error"})

    async def handle_update_config(self, request):
        try:
            data = await request.json()
            log("Web: Remote config update received", "WARNING")
            await update_remote_config(data)
            await self.update_config_from_db()
            return web.json_response({"status": "success"})
        except Exception as e:
            log(f"Web: Config update failed: {e}", "ERROR")
            return web.json_response({"status": "error"}, status=400)

    # --- ANALYTICS & NEURAL ---
    def _calculate_hyper_analytics(self):
        try:
            if len(self.synaptic_history) < 10: return None
            prices = np.array([h['price'] for h in self.synaptic_history])
            fei = np.abs(prices[-1] - prices[0]) / np.sum(np.abs(np.diff(prices)))
            return {"market_state": "TRENDING" if fei > 0.5 else "CHAOTIC", "fei": round(float(fei), 4)}
        except: return None

    async def fetch_neural_strategy(self, market_snapshot):
        if not self.ai_key: 
            log("Neural: AI Key missing, skipping analysis", "WARNING")
            return {"cmd": "WAIT"}
        
        log("Neural: Sending market data to GPT-4o...", "INFO")
        try:
            hyper = self._calculate_hyper_analytics()
            res = await asyncio.wait_for(openai.ChatCompletion.acreate(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Analyze market. Output JSON ONLY: {\"cmd\": \"BUY\"/\"WAIT\", \"amt\": float}"},
                    {"role": "user", "content": json.dumps({"market": market_snapshot, "hyper": hyper})}
                ],
                response_format={ "type": "json_object" }
            ), timeout=15)
            decision = json.loads(res.choices[0].message.content)
            log(f"Neural Decision: {decision.get('cmd')} (Amt: {decision.get('amt')})", "SUCCESS")
            return decision
        except Exception as e:
            log(f"Neural Error: {e}", "ERROR")
            return {"cmd": "WAIT"}

    async def dispatch_hft_pulse(self, wallet, plan):
        if not self.pool_addr: 
            log("TON: Pool address missing!", "ERROR")
            return False
        
        try:
            amt = float(plan.get('amt', 0))
            nano_amt = int(amt * 1e9)
            log(f"TON: Dispatching {amt} TON to Vault with swap payload...", "INFO")
            
            swap_payload = (BeginCell()
                            .store_uint(0xea06185d, 32) # DeDust Swap Op
                            .store_uint(int(time.time() + 150), 64)
                            .store_coins(nano_amt)
                            .store_address(self.pool_addr)
                            .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
            
            await wallet.transfer(destination=self.vault_ton, amount=nano_amt + int(0.3e9), body=swap_payload)
            self.total_ops += 1
            log(f"TON: Pulse successful. Op #{self.total_ops}", "SUCCESS")
            return True
        except Exception as e:
            log(f"TON: Pulse failed: {e}", "ERROR")
            return False

    # --- RUNNERS ---
    async def start_web_server(self):
        log("Starting Web Server on port 3000...", "INFO")
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_headers="*", allow_credentials=True, expose_headers="*")})
        
        app.router.add_get('/', self.handle_index)
        app.router.add_get('/api/stats', self.handle_get_stats)
        app.router.add_post('/api/config', self.handle_update_config)
        
        if os.path.exists('static'):
            app.router.add_static('/static/', path='static', name='static')

        for route in list(app.router.routes()): cors.add(route)
        
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, '0.0.0.0', 3000).start()
        log("Web Server is ONLINE", "SUCCESS")

    async def core_loop(self):
        log("Entering Core Loop...", "CORE")
        
        # 1. DB Init
        while True:
            try:
                log("Connecting to Database...", "INFO")
                await init_db()
                log("Database connected", "SUCCESS")
                break
            except Exception as e:
                log(f"Database connection failed: {e}. Retrying in 5s...", "ERROR")
                await asyncio.sleep(5)

        # 2. Web Task
        asyncio.create_task(self.start_web_server())

        while self.is_active:
            try:
                # 3. Config Check
                if not await self.update_config_from_db():
                    self.last_status = "WAITING_CONFIG"
                    await asyncio.sleep(10)
                    continue

                # 4. TON Init
                log("Connecting to TON Mainnet...", "INFO")
                client = LiteClient.from_mainnet_config()
                await client.start()
                wallet = await WalletV4R2.from_mnemonic(client, self.mnemonic.split())
                log(f"Wallet Active: {wallet.address}", "SUCCESS")

                while self.is_active:
                    try:
                        log("--- Iteration Start ---", "INFO")
                        market_state = await get_market_state()
                        p_curr = market_state['current_metrics']['price_ton']
                        self.synaptic_history.append({"price": p_curr, "time": time.time()})
                        if len(self.synaptic_history) > 500: self.synaptic_history.pop(0)

                        balance = (await wallet.get_balance()) / 1e9
                        log(f"Balance: {balance:.2f} TON | History: {len(self.synaptic_history)} pts", "INFO")

                        plan = await self.fetch_neural_strategy(market_state)
                        
                        if plan.get('cmd') == "BUY" and balance > (float(plan.get('amt', 0)) + 1.0):
                            if await self.dispatch_hft_pulse(wallet, plan):
                                await log_ai_action(plan, market_state['current_metrics'])
                        
                        await asyncio.sleep(15)

                    except Exception as inner_e:
                        log(f"Iteration error: {inner_e}", "ERROR")
                        await asyncio.sleep(5)
                        break # Re-init TON

            except Exception as outer_e:
                log(f"Main loop critical error: {outer_e}", "ERROR")
                traceback.print_exc()
                await asyncio.sleep(10)

if __name__ == "__main__":
    while True:
        try:
            overlord = OmniNeuralOverlord()
            asyncio.run(overlord.core_loop())
        except KeyboardInterrupt:
            log("Manual shutdown detected. Exiting.", "WARNING")
            break
        except Exception as fatal:
            log(f"FATAL EXCEPTION: {fatal}. Restarting kernel...", "ERROR")
            time.sleep(5)
