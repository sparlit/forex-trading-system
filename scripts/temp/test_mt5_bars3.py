
import asyncio
import MetaTrader5 as mt5
from src.infra.config.settings import settings

async def test():
    # Initialize MT5
    initialized = mt5.initialize(
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
    )
    print("MT5 initialized:", initialized)
    
    # Check if we can get rates for all timeframes
    for tf_name, tf_val in [("1m", mt5.TIMEFRAME_M1), ("5m", mt5.TIMEFRAME_M5), ("1h", mt5.TIMEFRAME_H1)]:
        rates = mt5.copy_rates_from_pos("EURUSD", tf_val, 0, 2)
        print(f"{tf_name}: {len(rates) if rates else 0} bars")
        if rates is not None and len(rates) >= 2:
            r = rates[1]
            print(f"  Bar 1: time={r['time']} O={r['open']} H={r['high']} L={r['low']} C={r['close']}")
    
    mt5.shutdown()

asyncio.run(test())
