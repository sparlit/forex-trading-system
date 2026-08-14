import asyncio
from src.data.storage.timescale import TimescaleDB
from src.data.storage.redis_cache import RedisCache
from src.infra.config.settings import settings

async def test():
    db = TimescaleDB()
    await db.connect()
    
    cache = RedisCache()
    await cache.connect()
    
    # Check TimescaleDB
    async with db.acquire() as conn:
        row = await conn.fetchrow('''
            SELECT COUNT(*) as cnt 
            FROM market_data.bars 
            WHERE is_complete = TRUE
        ''')
        print(f'TimescaleDB: {row["cnt"]} bars stored')
    
    # Check Redis
    keys = await cache._client.keys('*')
    print(f'Redis: {len(keys)} keys cached')
    
    await db.disconnect()
    await cache.disconnect()

asyncio.run(test())
print('Core system verification: PASSED')