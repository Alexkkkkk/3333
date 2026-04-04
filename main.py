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

# TON Либы
from pytoniq import LiteClient, WalletV4R2, BeginCell, Address
# Модули БД
from database import init_db, log_ai_action, get_market_state, get_stats_for_web, get_pool, add_profit_record

load_dotenv()
openai.api_key = os.getenv("AI_API_KEY")

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        # Конфиг TON
        self.pool_addr = Address(os.getenv('DEDUST_POOL'))
        self.vault_ton = Address(os.getenv('DEDUST_VAULT_TON'))
        
        self.synaptic_history = []
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        self.backlog = asyncio.Queue()

    # --- ANALYTICS ENGINE ---
    def _calculate_hyper_analytics(self):
        """Спектральный и фрактальный анализ рыночных данных."""
        if len(self.synaptic_history) < 20: return None
        
        prices = np.array([h['price'] for h in self.synaptic_history])
        curr = prices[-1]
        
        # 1. Fractal Efficiency (FEI)
        path_length = np.sum(np.abs(np.diff(prices)))
        radial_dist = np.abs(prices[-1] - prices[0])
        fei = radial_dist / path_length if path_length > 0 else 0

        # 2. Spectral Purity (FFT) - поиск циклов китов
        fft_data = np.abs(np.fft.fft(prices))
        signal_purity = np.max(fft_data) / np.mean(fft_data) if np.mean(fft_data) > 0 else 0

        # 3. Probability Collapse (Eigenvalues)
        matrix = np.column_stack([prices[1:], prices[:-1]])
        cov = np.cov(matrix.T)
        eigenvalues = np.linalg.eigvals(cov)
        prob_collapse = np.max(eigenvalues) / np.sum(eigenvalues) if np.sum(eigenvalues) > 0 else 0
        
        # 4. Z-Score & Gravity
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
        hyper = self._calculate_hyper_analytics()
        
        prompt = {
            "core_id": self.core_id,
            "market": market_snapshot['current_metrics'],
            "memory": market_snapshot['recent_memory'],
            "singularity": hyper,
            "mission": "Execute hyper-precise entry. Exploit market imbalances."
        }

        try:
            res = await openai.ChatCompletion.acreate(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are OMNI-SINGULARITY. CMD: [BUY/PUMP/SHIELD/WAIT]. Output JSON ONLY. Accuracy: 100%."},
                    {"role": "user", "content": json.dumps(prompt)}
                ],
                response_format={ "type": "json_object" },
                temperature=0.1
            )
            logic = json.loads(res.choices[0].message.content)
            
            return {
                "cmd": str(logic.get("cmd", "WAIT")).upper(),
                "amt": min(float(logic.get("amt", 0)), 50.0),
                "delay": max(int(logic.get("delay", 15)), 5),
                "urgency": max(min(int(logic.get("urgency", 1)), 5), 1),
                "reason": str(logic.get("reason", "Scanning fractal waves")),
                "confidence": logic.get("confidence_pct", 0)
            }
        except Exception as e:
            return {"cmd": "WAIT", "amt": 0, "delay": 20, "reason": f"Neural Lag: {e}"}

    async def dispatch_hft_pulse(self, wallet, plan, market):
        """Отправка транзакции со встроенным Jitter (анти-бот защита)."""
        amt = plan['amt']
        nano_amt = int(amt * 1e9)
        adjusted_gas = int(0.25e9 + (plan['urgency'] * 0.03e9))

        swap_payload = (BeginCell()
                        .store_uint(0xea06185d, 32) # Op-code DeDust
                        .store_uint(int(time.time() + 150), 64)
                        .store_coins(nano_amt)
                        .store_address(self.pool_addr)
                        .store_uint(0, 1).store_coins(0).store_maybe_ref(None).end_cell())
        try:
            jitter = int(nano_amt * (1 + random.uniform(-0.015, 0.015)))
            await asyncio.wait_for(
                wallet.transfer(destination=self.vault_ton, amount=jitter + adjusted_gas, body=swap_payload), 
                timeout=25.0
            )
            self.total_ops += 1
            self.last_status = f"EXECUTED_{plan['cmd']}"
            return True
        except Exception as e:
            self.last_status = "PULSE_ERROR"
            print(f"\n🚨 [DISPATCH ERROR]: {e}")
            return False

    # --- WEB SERVER ---
    async def start_web_server(self):
        app = web.Application()
        aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_headers="*")})
        app.router.add_get('/api/stats', lambda r: web.json_response(get_stats_for_web()))
        
        if os.path.exists('static'): 
            app.router.add_static('/', path='static', name='static')
        
        runner = web.AppRunner(app); await runner.setup()
        await web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 3000))).start()
        print(f"\033[94m🌐 [WEB] Terminal Ready: http://0.0.0.0:3000\033[0m")

    async def telemetry_worker(self):
        """Фоновый воркер логов."""
        while self.is_active:
            task = await self.backlog.get()
            try: await log_ai_action(task['strategy'], task['market'])
            except: pass
            finally: self.backlog.task_done()

    # --- CORE LOOP ---
    async def core_loop(self):
        await init_db()
        asyncio.create_task(self.telemetry_worker())
        await self.start_web_server()

        client = LiteClient.from_mainnet_config(); await client.start()
        wallet = await WalletV4R2.from_mnemonic(client, os.getenv('MNEMONIC').split())
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"\033[95m--- 🌀 OMNI NEURAL CORE V-INFINITY : SINGULARITY ONLINE ---\033[0m")

        while self.is_active:
            try:
                # Получаем расширенный стейт из базы (тренды + история)
                market_state = await get_market_state()
                p_curr = market_state['current_metrics']['price_ton']
                
                # Обновляем локальную синаптическую историю для FFT
                self.synaptic_history.append({"price": p_curr, "time": time.time()})
                if len(self.synaptic_history) > 200: self.synaptic_history.pop(0)

                balance = (await wallet.get_balance()) / 1e9
                sys.stdout.write(f"\r\033[96m[ BAL: {balance:.2f} | OPS: {self.total_ops} | STATUS: {self.last_status} ]\033[0m")
                sys.stdout.flush()

                plan = await self.fetch_neural_strategy(market_state)
                
                if plan['cmd'] in ["BUY", "PUMP", "SHIELD"] and balance > (plan['amt'] + 3.0):
                    if await self.dispatch_hft_pulse(wallet, plan, market_state):
                        await self.backlog.put({"strategy": plan, "market": market_state['current_metrics']})
                else:
                    if random.random() < 0.1: # Логируем аналитику в 10% простоев
                        await log_ai_action(plan, market_state['current_metrics'])

                await asyncio.sleep(max(5, plan['delay'] + random.randint(-2, 3)))

            except Exception as e:
                self.last_status = "RECALIBRATING"
                print(f"\n[LOOP ERROR]: {e}")
                await asyncio.sleep(10)

if __name__ == "__main__":
    try: asyncio.run(OmniNeuralOverlord().core_loop())
    except KeyboardInterrupt: print("\033[91m\n🔌 Overmind Offline.\033[0m")
