import asyncio
import redis.asyncio as redis
from src.infra.config.settings import settings

async def test():
    r = redis.from_url(settings.redis_url, decode_responses=True)
    keys = await r.keys("*")
    print(f"Keys in Redis: {len(keys)}")
    for k in keys:
        val = await r.get(k)
        print(f"  {k}: {val[:100]}...")
    await r.close()

asyncio.run(test())