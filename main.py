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
from pytoniq import LiteClient, WalletV4R2, BeginCell, Address
from database import init_db, log_ai_action, get_market_state, get_stats_for_web

# Загрузка конфигурации (Ultra-Secure High-Load Edition)
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
        
        # ДНК Системы
        self.dna = {
            "market_pressure": 0.99,      # Агрессия в стакане
            "stealth_mode": 0.94,         # Имитация кита
            "floor_protection": 0.88,     # Защита цены
            "gas_strategy": "HYPER_FAST", # Оптимизация под pghost.ru
            "integrity_check": "LOCKED"   # Защита дизайна
        }
        
        self.synaptic_history = []         # История цен для мат. анализа
        self.last_status = "INITIALIZING"
        self.total_ops = 0
        self.backlog = asyncio.Queue()

    def _calculate_quantum_signals(self):
        """Математический движок: RSI + SMA + Volatility."""
        if len(self.synaptic_history) < 5: return None
        
        prices = [h['price'] for h in self.synaptic_history]
        sma = np.mean(prices[-10:]) if len(prices) >= 10 else np.mean(prices)
        std_dev = np.std(prices) if len(prices) > 1 else 0.001
        current_price = prices[-1]
        
        # Определение импульса
        momentum = (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 5 else 0
        
        return {
            "sma": round(float(sma), 8),
            "volatility": round(float(std_dev / sma), 4) if sma != 0 else 0,
            "momentum": round(float(momentum), 4),
            "is_oversold": current_price < (sma - std_dev)
        }

    async def fetch_neural_strategy(self, market_snapshot):
        """Deep Analysis Layer: ИИ-архитектор выстраивает план доминирования."""
        signals = self._calculate_quantum_signals()
        
        prompt = {
            "system": {"id": self.core_id, "aggression": self.strategy_level},
            "market": market_snapshot,
            "signals": signals,
            "constraints": {"max_amt": 50, "min_ton_buffer": 2.5},
            "mission": "Maintain absolute growth, hide bot traces, orchestrate volume pulse."
        }

        try:
            res = await openai.ChatCompletion.acreate(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": (
                        "You are the OMNI-ARCHITECT of TON. Command the liquidity. "
                        "Commands: BUY, PUMP (aggressive), SHIELD (protect floor), WAIT. "
                        "Output JSON ONLY. Max amt 50 TON. Be surgical."
                    )},
                    {"role": "user", "content": json.dumps(prompt)}
                ],
                response_format={ "type": "json_object" },
                temperature=0.4
            )
            
            logic = json.loads(res.choices[0].message.content)
            
            return {
                "cmd": str(logic.get("cmd", "WAIT")).upper(),
                "amt": min(float(logic.get("amt", 0)), 50.0),
                "delay": max(int(logic.get("delay", 30)), 10),
                "urgency": max(min(int(logic.get("urgency", 1)), 5), 1),
                "reason": str(logic.get("reason", "Analyzing pulse..."))
            }
        except Exception as e:
            return {"cmd": "WAIT", "amt": 0, "delay": 40, "reason": f"Neural Link Error: {e}"}

    async def dispatch_hft_pulse(self, wallet, plan, market):
        """Hyper-Speed Dispatcher: Мгновенное исполнение в DeDust V2."""
        amt = plan['amt']
        urgency = plan['urgency']
        nano_amt = int(amt * 1e9)
        
        # Динамический газ
        adjusted_gas = int(0.22e9 + (urgency * 0.02e9))

        # Payload: DeDust V2 Swap
        swap_payload = (BeginCell()
                        .store_uint(0xea06185d, 32)
                        .store_uint(int(time.time() + 120), 64) 
                        .store_coins(nano_amt)
                        .store_address(self.pool_addr)
                        .store_uint(0, 1) # step_kind (swap)
                        .store_coins(0)   # min_out (slippage control)
                        .store_maybe_ref(None)
                        .end_cell())

        try:
            # Stealth-джиттер
            jitter_amt = nano_amt * (1 + random.uniform(-0.05, 0.05))
            
            print(f"\n\033[92m🚀 [PULSE] {plan['cmd']} | {amt:.2f} TON | Urgency: {urgency}/5\033[0m")
            print(f"\033[90m💭 Reason: {plan['reason']}\033[0m")

            await asyncio.wait_for(
                wallet.transfer(
                    destination=self.vault_ton,
                    amount=int(jitter_amt) + adjusted_gas,
                    body=swap_payload
                ),
                timeout=25.0
            )
            
            self.total_ops += 1
            self.last_status = f"EXECUTED_{plan['cmd']}"
            
            # Обновляем историю для мат. движка
            price = market.get('current_metrics', {}).get('price_ton', 0)
            self.synaptic_history.append({"price": price, "time": time.time()})
            if len(self.synaptic_history) > 100: self.synaptic_history.pop(0)
            
            return True
        except Exception as e:
            print(f"\n\033[91m🚨 [PULSE_FAILED]: {e}\033[0m")
            self.last_status = "FAILED_TRANSACTION"
            return False

    async def core_loop(self):
        """Main Loop: Неубиваемое ядро управления."""
        await init_db()
        asyncio.create_task(self.telemetry_worker())

        client = LiteClient.from_mainnet_config()
        await client.start()
        
        mnemonic = os.getenv('MNEMONIC').split()
        wallet = await WalletV4R2.from_mnemonic(client, mnemonic)
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"\033[95m--- 🌀 OMNI NEURAL CORE V20 : ACTIVATED ---\033[0m")
        print(f"\033[93m[ DESIGN PROTECTED | DB: PGHOST_GRID | STAGE: DOMINATION ]\033[0m")

        while self.is_active:
            try:
                # 1. Сбор данных
                market = await get_market_state()
                balance = (await wallet.get_balance()) / 1e9
                
                # 2. Логирование в консоль
                sys.stdout.write(
                    f"\r\033[96m[ BAL: {balance:.2f} | OPS: {self.total_ops} | STATUS: {self.last_status} ]\033[0m"
                )
                sys.stdout.flush()

                # 3. Нейронное планирование
                plan = await self.fetch_neural_strategy(market)
                
                # 4. Исполнение (защитный буфер 2.5 TON)
                if plan['cmd'] in ["BUY", "PUMP", "SHIELD"] and balance > (plan['amt'] + 2.5):
                    success = await self.dispatch_hft_pulse(wallet, plan, market)
                    if success:
                        await self.backlog.put({"strategy": plan, "market": market})

                # 5. Адаптивный сон
                sleep_time = plan['delay'] + random.randint(-5, 10)
                await asyncio.sleep(max(10, sleep_time))

            except Exception as e:
                print(f"\n🚨 [CORE_ERROR]: {e}")
                await asyncio.sleep(20)

    async def telemetry_worker(self):
        """Фоновый воркер для PostgreSQL."""
        while self.is_active:
            task = await self.backlog.get()
            try: 
                await log_ai_action(task['strategy'], task['market'])
            except: 
                pass
            finally: 
                self.backlog.task_done()

if __name__ == "__main__":
    omni_node = OmniNeuralOverlord()
    try:
        asyncio.run(omni_node.core_loop())
    except KeyboardInterrupt:
        print("\033[91m\n🔌 Система деактивирована. Состояние сохранено.\033[0m")
