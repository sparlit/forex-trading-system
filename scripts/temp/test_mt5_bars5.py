
import asyncio
import MetaTrader5 as mt5
from src.infra.config.settings import settings
from src.data.models import Timeframe

async def test():
    # Initialize MT5
    initialized = mt5.initialize(
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
    )
    print("MT5 initialized:", initialized)
    
    # Get rates for multiple timeframes and check if they're complete
    for tf_name, tf_val in [("1m", mt5.TIMEFRAME_M1), ("5m", mt5.TIMEFRAME_M5), ("1h", mt5.TIMEFRAME_H1)]:
        rates = mt5.copy_rates_from_pos("EURUSD", tf_val, 0, 5)
        rate_count = len(rates) if rates is not None else 0
        print(f"{tf_name}: {rate_count} bars")
        if rates is not None and rate_count >= 2:
            for i, r in enumerate(rates):
                print(f"  Bar {i}: time={r['time']} O={r['open']} H={r['high']} L={r['low']} C={r['close']} V={r['real_volume'] if r['real_volume'] > 0 else r['tick_volume']} spread={r['spread']}")
    
    mt5.shutdown()

asyncio.run(test())
