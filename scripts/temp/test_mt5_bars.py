
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
    
    ti = mt5.terminal_info()
    print("Terminal connected:", ti.connected if ti else None)
    
    sym = mt5.symbol_info("EURUSD")
    print("EURUSD:", sym is not None)
    if sym:
        print("  Visible:", sym.visible)
        print("  Trade mode:", sym.trade_mode)
    
    rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M1, 0, 5)
    print("EURUSD M1 rates:", len(rates) if rates is not None else "None")
    if rates is not None and len(rates) > 0:
        for r in rates[:3]:
            print(r)
    
    rates5 = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M5, 0, 3)
    print("EURUSD M5 rates:", len(rates5) if rates5 is not None else "None")
    
    mt5.shutdown()

asyncio.run(test())
