import asyncio
import os
import json
import time
import openai
import sys
import random
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from aiohttp import web
import aiohttp_cors

# --- УЛЬТРА-ЗАЩИЩЕННЫЙ ИМПОРТ TON ЛИБ ---
try:
    from pytoniq import LiteClient, WalletV4R2, Address
    try:
        from pytoniq.core import BeginCell
    except (ImportError, ModuleNotFoundError):
        from pytoniq import BeginCell
except ImportError:
    print("\033[91m🚨 [FATAL]: pytoniq is not installed. Check requirements.txt!\033[0m")
    sys.exit(1)

# Модули БД (Убедись, что в database.py есть функция load_remote_config)
from database import init_db, log_ai_action, get_market_state, get_stats_for_web, load_remote_config

load_dotenv()

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        # Динамические параметры (инициализируются из БД)
        self.pool_addr = None
        self.vault_ton = Address("EQCt0-Ba6Y_9_6p20tH_E_Oq_H_O_O_O_O_O_O_O_O_O_O_O_O")
        self.mnemonic = None
        self.ai_key = None
        
        self.synaptic_history = []
        self.last_status = "WAITING_FOR_CONFIG"
        self.total_ops = 0
        self.backlog = asyncio.Queue()

    async def update_config_from_db(self):
        """Механизм подтяжки настроек из админки (БД)"""
        try:
            cfg = await load_remote_config()
            if cfg:
                self.mnemonic = cfg.get('mnemonic')
                self.ai_key = cfg.get('ai_api_key')
                openai.api_key = self.ai_key
                
                pool_raw = cfg.get('dedust_pool')
                if pool_raw:
                    self.pool_addr = Address(pool_raw)
                
                self.strategy_level = cfg.get('ai_strategy_level', 10)
                return True
            return False
        except Exception as e:
            print(f"\033[91m🚨 [DB CONFIG ERROR]: {e}\033[0m")
            return False

    # --- АНАЛИТИЧЕСКИЙ ДВИЖОК ---
    def _calculate_hyper_analytics(self):
        if len(self.synaptic_history) < 20: return None
        prices = np.array([h['price'] for h in self.synaptic_history])
        curr = prices[-1]
        
        path_length = np.sum(np.abs(np.diff(prices)))
        radial_dist = np.abs(prices[-1] - prices[0])
        fei = radial_dist / path_length if path_length > 0 else 0

        fft_data = np.abs(np.fft.fft(prices))
        signal_purity = np.max(fft_data) / np.mean(fft_data) if np.mean(fft_data) > 0 else 0

        matrix = np.column_stack([prices[1:], prices[:-1]])
        cov = np.cov(matrix.T)
        eigenvalues = np.linalg.eigvals(cov)
        prob_collapse = np.max(eigenvalues) / np.sum(eigenvalues) if np.sum(eigenvalues) > 0 else 0
        
        sma = np.mean(prices[-15:])
        std = np.std(prices)
        z_score = (curr - sma) / std if std > 0 else 0
        gravity = np.average(prices, weights=np.linspace(0.1, 1.0, len(prices)))

        return {
            "fractal_efficiency": round(float(fei), 4),
            "signal_purity": round(float(signal_purity), 2),
            "prob_collapse": round(float(prob_collapse), 4),
            "market_state": "TRENDING" if fei > 0.5 else "CHAOTIC",
            "gravity_price": round(float(gravity), 8),
            "z_score": round(float(z_score), 2),
            "neural_confidence": round(float(prob_collapse * 100), 2)
        }

    async def fetch_neural_strategy(self, market_snapshot):
        if not self.ai_key: return {"cmd": "WAIT", "reason": "No AI Key in DB"}
        
        hyper = self._calculate_hyper_analytics()
        prompt = {
            "core_id": self.core_id,
            "market": market_snapshot['current_metrics'],
            "singularity": hyper,
            "strategy_level": self.strategy_level
        }

        try:
            res = await openai.ChatCompletion.acreate(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are OMNI-SINGULARITY. Output JSON ONLY. [BUY/WAIT]."},
                    {"role": "user", "content": json.dumps(prompt)}
                ],
                response_format={ "type": "json_object" },
                temperature=0.1
            )
            return json.loads(res.choices[0].message.content)
        except Exception as e:
            return {"cmd": "WAIT", "amt": 0, "delay": 20, "reason": f"Neural Lag: {e}"}

    async def dispatch_hft_pulse(self, wallet, plan):
        if not self.pool_addr: return False
        
        amt = float(plan.get('amt', 0))
        nano_amt = int(amt * 1e9)
        
        swap_payload = (BeginCell()
                        .store_uint(0xea06185d, 32)
                        .store_uint(int(time.time() + 150), 64)
                        .store_coins(nano_amt)
                        .store_address(self.pool_addr)
                        .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
        try:
            await wallet.transfer(destination=self.vault_ton, amount=nano_amt + int(0.3e9), body=swap_payload)
            self.total_ops += 1
            self.last_status = "EXECUTED"
            return True
        except Exception as e:
            print(f"🚨 [DISPATCH ERROR]: {e}")
            return False

    async def start_web_server(self):
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")})
        
        resource = app.router.add_get('/api/stats', lambda r: web.json_response(get_stats_for_web()))
        cors.add(resource)
        
        if os.path.exists('static'): 
            app.router.add_static('/', path='static', name='static', show_index=True)
        
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv('PORT', 3000))
        await web.TCPSite(runner, '0.0.0.0', port).start()
        print(f"\033[94m🌐 [WEB] Terminal Ready: http://0.0.0.0:{port}\033[0m")

    async def core_loop(self):
        await init_db()
        await self.start_web_server()

        print(f"\033[95m--- 🌀 OMNI NEURAL CORE : DATABASE-DRIVEN MODE ---\033[0m")

        while self.is_active:
            try:
                # 1. Синхронизация с админкой
                if not await self.update_config_from_db():
                    print("\r\033[93m⌛ Ожидание конфигурации в базе данных...\033[0m", end="")
                    await asyncio.sleep(10)
                    continue

                # 2. Инициализация кошелька, если конфигурация подгружена
                client = LiteClient.from_mainnet_config()
                await client.start()
                wallet = await WalletV4R2.from_mnemonic(client, self.mnemonic.split())

                # 3. Основной цикл работы
                while self.is_active:
                    market_state = await get_market_state()
                    p_curr = market_state['current_metrics']['price_ton']
                    self.synaptic_history.append({"price": p_curr, "time": time.time()})
                    
                    balance = (await wallet.get_balance()) / 1e9
                    sys.stdout.write(f"\r\033[96m[ BAL: {balance:.2f} | OPS: {self.total_ops} | ADDR: {self.pool_addr} ]\033[0m")
                    sys.stdout.flush()

                    plan = await self.fetch_neural_strategy(market_state)
                    
                    if plan.get('cmd') == "BUY" and balance > (float(plan.get('amt', 0)) + 1.0):
                        await self.dispatch_hft_pulse(wallet, plan)
                    
                    # Периодическая проверка обновления настроек в БД
                    if self.total_ops % 5 == 0: await self.update_config_from_db()
                    
                    await asyncio.sleep(15)

            except Exception as e:
                self.last_status = "RECALIBRATING"
                print(f"\n[LOOP ERROR]: {e}")
                await asyncio.sleep(10)

if __name__ == "__main__":
    try: 
        asyncio.run(OmniNeuralOverlord().core_loop())
    except KeyboardInterrupt: 
        print("\033[91m\n🔌 Overmind Offline.\033[0m")
