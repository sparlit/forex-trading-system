
import asyncio
from src.data.ingest.mt5_connector import MT5Provider
from src.data.models import Timeframe
from src.data.providers.base import SubscriptionRequest
from src.infra.config.settings import settings

async def test():
    provider = MT5Provider(
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
    )
    await provider.connect()
    
    request = SubscriptionRequest(symbols=["EURUSD"], timeframes=[Timeframe.M1])
    print("Subscribing to bars...")
    count = 0
    async for bar in provider.subscribe_bars(request):
        print(f"Got bar: {bar.symbol} {bar.timeframe} O={bar.open} H={bar.high} L={bar.low} C={bar.close}")
        count += 1
        if count >= 5:
            break
    
    await provider.disconnect()

asyncio.run(test())
