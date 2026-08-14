import asyncio
from src.ui.bloomberg_terminal import BloombergTerminal

async def test():
    app = BloombergTerminal()
    await app.init_connections()
    print('init_connections done')
    await app.refresh_market_data()
    print('refresh_market_data done')
    print('Market data:', app.market_data)
    await app.redis_client.aclose()

asyncio.run(test())
print('Done')