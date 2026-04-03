import asyncio
import os
import random
import json
import openai
from dotenv import load_dotenv
from pytoniq import LiteClient, WalletV4R2, BeginCell, Address
from database import init_db, log_ai_action, get_market_state

load_dotenv()
openai.api_key = os.getenv("AI_API_KEY")

class NeuralDeDustBot:
    def __init__(self):
        self.is_active = True
        self.pool_addr = Address(os.getenv('DEDUST_POOL'))
        self.vault_ton = Address(os.getenv('DEDUST_VAULT_TON'))

    async def get_ai_command(self, market_data):
        """Нейросеть принимает решение на основе реальных цифр"""
        prompt = f"Data: {market_data}. Goal: Moon Growth. Output JSON: {{'cmd': 'BUY', 'amt': 1.2, 'delay': 30, 'reason': '...'}}"
        try:
            resp = await openai.ChatCompletion.acreate(
                model="gpt-4-turbo",
                messages=[{"role": "system", "content": "You are a TON HFT Whale."},
                          {"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            return json.loads(resp.choices[0].message.content)
        except:
            return {"cmd": "WAIT", "amt": 0, "delay": 60}

    async def execute_trade(self, wallet, amount):
        """Прямой прострел в DeDust V2 за < 1.1 сек"""
        nano_amt = int(amount * 1e9)
        # Формируем Payload Swap (Op: 0xea06185d)
        payload = (BeginCell()
                .store_uint(0xea06185d, 32)
                .store_uint(0, 64)
                .store_coins(nano_amt)
                .store_address(self.pool_addr)
                .store_uint(0, 1) # Direct
                .store_coins(0)   # Market
                .end_cell())
        
        await wallet.transfer(
            destination=self.vault_ton,
            amount=nano_amt + int(0.15 * 1e9),
            body=payload
        )

    async def run(self):
        client = LiteClient.from_mainnet_config()
        await client.start()
        wallet = await WalletV4R2.from_mnemonic(client, os.getenv('MNEMONIC').split())
        
        print(f"🔥 NEURAL TERMINAL ONLINE: {wallet.address}")

        while self.is_active:
            try:
                # 1. Срез рынка
                state = await get_market_state()
                # 2. Мозг ИИ
                plan = await self.get_ai_command(state)
                
                print(f"🧠 AI: {plan['cmd']} | {plan['amt']} TON | {plan['reason']}")
                
                if plan['cmd'] in ["BUY", "PUMP", "SHIELD"]:
                    await self.execute_trade(wallet, plan['amt'])
                
                await log_ai_action(plan)
                await asyncio.sleep(plan['delay'])
                
            except Exception as e:
                print(f"⚠️ Ошибка: {e}")
                await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(init_db())
    bot = NeuralDeDustBot()
    asyncio.run(bot.run())
