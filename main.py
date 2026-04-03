import asyncio
import os
import random
import time
from dotenv import load_dotenv
from pytoniq import LiteClient, WalletV4R2, BeginCell, Address
from database import init_db, log_market_action

load_dotenv()

class DeDustDominator:
    def __init__(self):
        self.is_active = True
        self.vault_ton = Address(os.getenv('DEDUST_VAULT_TON'))
        self.pool_addr = Address(os.getenv('DEDUST_POOL'))

    async def build_dedust_payload(self, amount_nano):
        """Формирование бинарного Payload для DeDust Protocol V2 (Swap)"""
        # Op-code: 0xea06185d (DeDust V2 Swap)
        return (BeginCell()
                .store_uint(0xea06185d, 32) 
                .store_uint(0, 64)          # Query ID
                .store_coins(amount_nano)
                .store_address(self.pool_addr)
                .store_uint(0, 1)           # Swap type: Direct
                .store_coins(0)             # Slippage limit (0 = market)
                .store_maybe_ref(None)      
                .end_cell())

    async def market_pulse(self, wallet):
        """Создание 'зеленой свечи' и объема на DeDust"""
        amount = round(random.uniform(float(os.getenv('MIN_BUY_TON')), float(os.getenv('MAX_BUY_TON'))), 2)
        nano_amount = int(amount * 1e9)
        
        print(f"🔥 [PULSE] Атака на DeDust: {amount} TON...")
        
        payload = await self.build_dedust_payload(nano_amount)
        # Отправляем напрямую в Vault (самый быстрый путь исполнения)
        await wallet.transfer(
            destination=self.vault_ton,
            amount=nano_amount + int(0.15 * 1e9), # Сумма + Gas fee
            body=payload
        )
        
        await log_market_action("DEDUST_BUY", amount)

    async def strategy_loop(self, wallet):
        while self.is_active:
            try:
                await self.market_pulse(wallet)
                # Имитация человеческого поведения (рандомные задержки)
                wait = random.randint(int(os.getenv('DELAY_MIN')), int(os.getenv('DELAY_MAX')))
                await asyncio.sleep(wait)
            except Exception as e:
                print(f"⚠️ [SYSTEM_ERROR] Перезагрузка ядра: {e}")
                await asyncio.sleep(10)

    async def start(self):
        # Подключение к LiteServer 2026 (самая высокая скорость в TON)
        client = LiteClient.from_mainnet_config()
        await client.start()
        
        wallet = await WalletV4R2.from_mnemonic(client, os.getenv('MNEMONIC').split())
        print(f"⚡ DOMINATOR ACTIVE | КОШЕЛЕК: {wallet.address}")

        await self.strategy_loop(wallet)

if __name__ == "__main__":
    asyncio.run(init_db())
    engine = DeDustDominator()
    asyncio.run(engine.start())
