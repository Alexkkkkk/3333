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

# Блок TON библиотек
from pytoniq import LiteClient, WalletV4R2, BeginCell, Address
# Твои локальные модули
from database import init_db, log_ai_action, get_market_state, get_stats_for_web, get_pool

# Загрузка конфигурации
load_dotenv()
openai.api_key = os.getenv("AI_API_KEY")

class OmniNeuralOverlord:
    def __init__(self):
        self.is_active = True
        self.session_start = time.time()
        self.core_id = f"OMNI-{os.urandom(4).hex().upper()}"
        
        # Конфигурация из .env
        self.pool_addr = Address(os.getenv('DEDUST_POOL'))
        self.vault_ton = Address(os.getenv('DEDUST_VAULT_TON'))
        self.strategy_level = int(os.getenv('AI_STRATEGY_LEVEL', 10))
        
        # ДНК Системы (Аналитические коэффициенты)
        self.dna = {
            "market_pressure": 0.99,
            "stealth_mode": 0.94,
            "floor_protection": 0.88,
            "gas_strategy": "HYPER_FAST"
        }
        
        self.synaptic_history = []
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        self.backlog = asyncio.Queue()

    # --- МАТЕМАТИЧЕСКИЙ ДВИЖОК (Oracle Analytics) ---
    def _calculate_oracle_signals(self):
        """Вычисляет глубокие метрики: FVG, Z-Score и Энтропию."""
        if len(self.synaptic_history) < 10: return None
        
        prices = [h['price'] for h in self.synaptic_history]
        curr = prices[-1]
        
        # 1. Fair Value Gap (FVG) - Поиск "пустоты" ликвидности
        fvg_active = False
        magnet_price = None
        if len(prices) >= 3:
            p1, p2, p3 = prices[-3], prices[-2], prices[-1]
            # Если цена прыгнула вверх более чем на 1.5% и оставила разрыв
            if p3 > p1 * 1.015:
                fvg_active = True
                magnet_price = (p1 + p3) / 2

        # 2. Расчет волатильности и Z-Score
        sma = np.mean(prices[-15:]) if len(prices) >= 15 else np.mean(prices)
        std_dev = np.std(prices) if len(prices) > 1 else 0.0001
        z_score = (curr - sma) / std_dev if std_dev > 0 else 0
        
        # 3. Энтропия (Хаотичность потока)
        returns = np.diff(prices)
        entropy = np.std(returns) / np.abs(np.mean(returns)) if np.mean(returns) != 0 else 0

        return {
            "sma": round(float(sma), 8),
            "z_score": round(float(z_score), 2),
            "fvg_active": fvg_active,
            "magnet_price": round(float(magnet_price), 8) if magnet_price else None,
            "entropy_level": "STABLE" if entropy < 1.8 else "CHAOTIC",
            "momentum_pct": round(float(((prices[-1] - prices[-5])/prices[-5])*100), 2) if len(prices) >= 5 else 0,
            "reversal_probability": f"{min(abs(z_score) * 20, 99):.1f}%"
        }

    # --- ИИ ПЛАНИРОВАНИЕ ---
    async def fetch_neural_strategy(self, market_snapshot):
        oracle = self._calculate_oracle_signals()
        
        prompt = {
            "core_id": self.core_id,
            "market_metrics": market_snapshot['current_metrics'],
            "oracle_analysis": oracle,
            "recent_actions": market_snapshot.get('recent_memory', []),
            "constraints": {"max_amt": 50, "safety_buffer": 2.5}
        }

        try:
            res = await openai.ChatCompletion.acreate(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": (
                        "You are OMNI-ORACLE. High-frequency TON strategist. "
                        "CMD: BUY/PUMP/SHIELD/WAIT. Use oracle_analysis to find entry points. "
                        "If fvg_active is True, price will likely return to magnet_price. "
                        "Output JSON ONLY. Max amt 50."
                    )},
                    {"role": "user", "content": json.dumps(prompt)}
                ],
                response_format={ "type": "json_object" },
                temperature=0.2
            )
            logic = json.loads(res.choices[0].message.content)
            
            return {
                "cmd": str(logic.get("cmd", "WAIT")).upper(),
                "amt": min(float(logic.get("amt", 0)), 50.0),
                "delay": max(int(logic.get("delay", 30)), 10),
                "urgency": max(min(int(logic.get("urgency", 1)), 5), 1),
                "reason": str(logic.get("reason", "Oracle Synapse update")),
                "confidence": logic.get("confidence_pct", 0)
            }
        except Exception as e:
            return {"cmd": "WAIT", "amt": 0, "delay": 40, "reason": f"AI Error: {e}"}

    # --- ИСПОЛНЕНИЕ ТРАНЗАКЦИЙ (DeDust High-Speed) ---
    async def dispatch_hft_pulse(self, wallet, plan, market):
        amt = plan['amt']
        urgency = plan['urgency']
        nano_amt = int(amt * 1e9)
        adjusted_gas = int(0.25e9 + (urgency * 0.03e9))

        swap_payload = (BeginCell()
                        .store_uint(0xea06185d, 32)
                        .store_uint(int(time.time() + 120), 64)
                        .store_coins(nano_amt)
                        .store_address(self.pool_addr)
                        .store_uint(0, 1)
                        .store_coins(0)
                        .store_maybe_ref(None)
                        .end_cell())
        try:
            jitter_amt = int(nano_amt * (1 + random.uniform(-0.02, 0.02)))
            await asyncio.wait_for(
                wallet.transfer(
                    destination=self.vault_ton,
                    amount=jitter_amt + adjusted_gas,
                    body=swap_payload
                ), timeout=25.0
            )
            
            self.total_ops += 1
            self.last_status = f"SUCCESS_{plan['cmd']}"
            
            # Обновляем историю для Oracle
            price = market.get('current_metrics', {}).get('price_ton', 0)
            self.synaptic_history.append({"price": price, "time": time.time()})
            return True
        except Exception as e:
            self.last_status = "TX_FAIL"
            print(f"\n🚨 [TX_ERROR]: {e}")
            return False

    # --- WEB API ---
    async def handle_get_stats(self, request):
        stats = await get_stats_for_web()
        return web.json_response(stats)

    async def handle_update_settings(self, request):
        try:
            data = await request.json()
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute('''
                    UPDATE distribution_settings 
                    SET holders_pct = $1, staking_pct = $2, liquidity_pct = $3, treasury_pct = $4, updated_at = NOW()
                    WHERE label = 'default'
                ''', float(data['holders'])/100, float(data['staking'])/100, 
                     float(data['liquidity'])/100, float(data['treasury'])/100)
            return web.json_response({"status": "ok"})
        except:
            return web.json_response({"status": "error"})

    async def start_web_server(self):
        app = web.Application()
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")
        })
        app.router.add_get('/api/stats', self.handle_get_stats)
        app.router.add_post('/api/settings', self.handle_update_settings)
        if os.path.exists('static'):
            app.router.add_static('/', path='static', name='static')
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 3000)))
        await site.start()
        print(f"\033[94m🌐 [WEB] Oracle Interface: http://localhost:3000\033[0m")

    # --- WORKERS ---
    async def telemetry_worker(self):
        while self.is_active:
            task = await self.backlog.get()
            try: await log_ai_action(task['strategy'], task['market'])
            except: pass
            finally: self.backlog.task_done()

    # --- MAIN LOOP ---
    async def core_loop(self):
        await init_db()
        asyncio.create_task(self.telemetry_worker())
        await self.start_web_server()

        client = LiteClient.from_mainnet_config()
        await client.start()
        
        wallet = await WalletV4R2.from_mnemonic(client, os.getenv('MNEMONIC').split())
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"\033[95m--- 🌀 OMNI NEURAL CORE V28 : ORACLE ONLINE ---\033[0m")

        while self.is_active:
            try:
                market = await get_market_state()
                balance_data = await wallet.get_balance()
                balance = balance_data / 1e9
                
                sys.stdout.write(f"\r\033[96m[ BAL: {balance:.2f} | OPS: {self.total_ops} | STATUS: {self.last_status} ]\033[0m")
                sys.stdout.flush()

                plan = await self.fetch_neural_strategy(market)
                
                if plan['cmd'] in ["BUY", "PUMP", "SHIELD"] and balance > (plan['amt'] + 3.0):
                    if await self.dispatch_hft_pulse(wallet, plan, market):
                        await self.backlog.put({"strategy": plan, "market": market})
                else:
                    if random.random() < 0.15: # Логируем важные моменты ожидания
                        await self.backlog.put({"strategy": plan, "market": market})

                await asyncio.sleep(max(10, plan['delay'] + random.randint(-5, 10)))

            except Exception as e:
                self.last_status = "RECONNECTING"
                await asyncio.sleep(15)

if __name__ == "__main__":
    omni_node = OmniNeuralOverlord()
    try:
        asyncio.run(omni_node.core_loop())
    except KeyboardInterrupt:
        print("\033[91m\n🔌 Oracle Core Offline.\033[0m")
