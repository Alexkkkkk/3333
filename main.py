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

# Модули БД (Должны быть в database.py рядом с основным файлом)
from database import init_db, log_ai_action, get_market_state, get_stats_for_web, load_remote_config, update_remote_config

load_dotenv()

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        # Динамические параметры (грузятся из PostgreSQL)
        self.pool_addr = None
        self.vault_ton = Address("EQCt0-Ba6Y_9_6p20tH_E_Oq_H_O_O_O_O_O_O_O_O_O_O_O_O")
        self.mnemonic = None
        self.ai_key = None
        self.strategy_level = 10
        
        self.synaptic_history = []
        self.last_status = "WAITING_FOR_CONFIG"
        self.total_ops = 0

    async def update_config_from_db(self):
        """Синхронизация параметров с базой данных pghost.ru"""
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
                self.last_status = "ACTIVE"
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
                    {"role": "system", "content": "You are OMNI-SINGULARITY. Output JSON ONLY. Actions: [BUY/WAIT]."},
                    {"role": "user", "content": json.dumps(prompt)}
                ],
                response_format={ "type": "json_object" },
                temperature=0.1
            )
            return json.loads(res.choices[0].message.content)
        except Exception as e:
            return {"cmd": "WAIT", "reason": f"Neural Lag: {e}"}

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
            return True
        except Exception as e:
            print(f"🚨 [DISPATCH ERROR]: {e}")
            return False

    # --- WEB SERVER (FIXED PORT 3000) ---
    async def start_web_server(self):
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*"
            )
        })
        
        # Роуты API
        app.router.add_get('/api/stats', self.handle_get_stats)
        app.router.add_post('/api/config', self.handle_update_config)
        
        # Раздача статики (админки)
        if os.path.exists('static'): 
            app.router.add_static('/', path='static', name='static', show_index=True)
        
        # Применение CORS
        for route in list(app.router.routes()):
            cors.add(route)

        runner = web.AppRunner(app)
        await runner.setup()
        
        # ЖЕСТКИЙ ПОРТ 3000 ДЛЯ BOTHOST
        port = 3000 
        await web.TCPSite(runner, '0.0.0.0', port).start()
        print(f"\033[94m🌐 [WEB] QUANTUM Interface Ready: http://quantum.bothost.tech (PORT {port})\033[0m")

    async def handle_get_stats(self, request):
        stats = await get_stats_for_web()
        return web.json_response(stats)

    async def handle_update_config(self, request):
        try:
            data = await request.json()
            await update_remote_config(data) 
            await self.update_config_from_db() 
            return web.json_response({"status": "success", "message": "Core Reconfigured"})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=400)

    # --- MAIN LOOP ---
    async def core_loop(self):
        # 1. Инициализация БД
        await init_db()
        
        # 2. Запуск Веб-интерфейса
        await self.start_web_server()

        print(f"\033[95m--- 🌀 OMNI NEURAL CORE : SINGULARITY ONLINE ---\033[0m")

        while self.is_active:
            try:
                # 3. Проверка конфига
                if not await self.update_config_from_db():
                    print("\r\033[93m⌛ Ожидание конфигурации на https://quantum.bothost.tech ...\033[0m", end="")
                    await asyncio.sleep(10)
                    continue

                # 4. Соединение с TON
                client = LiteClient.from_mainnet_config()
                await client.start()
                wallet = await WalletV4R2.from_mnemonic(client, self.mnemonic.split())

                # 5. Цикл обработки рынка
                while self.is_active:
                    market_state = await get_market_state()
                    p_curr = market_state['current_metrics']['price_ton']
                    self.synaptic_history.append({"price": p_curr, "time": time.time()})
                    
                    if len(self.synaptic_history) > 200: self.synaptic_history.pop(0)

                    balance = (await wallet.get_balance()) / 1e9
                    sys.stdout.write(f"\r\033[96m[ BAL: {balance:.2f} | OPS: {self.total_ops} | PORT: 3000 ]\033[0m")
                    sys.stdout.flush()

                    # Нейронная стратегия
                    plan = await self.fetch_neural_strategy(market_state)
                    
                    if plan.get('cmd') == "BUY" and balance > (float(plan.get('amt', 0)) + 1.0):
                        if await self.dispatch_hft_pulse(wallet, plan):
                            await log_ai_action(plan, market_state['current_metrics'])
                    
                    # Проверка обновлений конфига в фоне каждые 5 минут
                    if int(time.time()) % 300 == 0:
                        await self.update_config_from_db()
                        
                    await asyncio.sleep(15)

            except Exception as e:
                print(f"\n[LOOP ERROR]: {e}")
                await asyncio.sleep(10)

if __name__ == "__main__":
    try: 
        asyncio.run(OmniNeuralOverlord().core_loop())
    except KeyboardInterrupt: 
        print("\033[91m\n🔌 Overmind Offline.\033[0m")
