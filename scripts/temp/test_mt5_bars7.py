
import asyncio
import MetaTrader5 as mt5
from src.infra.config.settings import settings

async def test():
    initialized = mt5.initialize(
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
    )
    print("MT5 initialized:", initialized)
    
    # Test the exact logic from _monitor_bars
    symbols = ["EURUSD", "GBPUSD", "USDJPY"]
    timeframes = ["1m", "5m", "1h"]
    
    for symbol in symbols:
        for tf_str in ["1m", "5m", "1h"]:
            tf_map = {"1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "1h": mt5.TIMEFRAME_H1}
            mt5_tf = tf_map[tf_str]
            print(f"Testing {symbol} {tf_str} -> MT5 TF: {mt5_tf}")
            
            rates = mt5.copy_rates_from_pos(symbol, tf_map[tf_str], 0, 2)
            rate_count = len(rates) if rates is not None else 0
            print(f"  {symbol} {tf_str}: {rate_count} bars")
            if rates is not None and rate_count >= 2:
                r = rates[1]
                print(f"  Bar: time={r['time']} O={r['open']} H={r['high']} L={r['low']} C={r['close']}")
    
    mt5.shutdown()

asyncio.run(test())
