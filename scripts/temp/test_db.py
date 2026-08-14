import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect(
        user="trader",
        password="changeme",
        database="market_data",
        host="127.0.0.1",
        port=5432
    )
    count = await conn.fetchval("SELECT count(*) FROM market_data.symbols")
    print("Symbols in DB:", count)
    await conn.close()

asyncio.run(test())
