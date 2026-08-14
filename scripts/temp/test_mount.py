import asyncio
from src.ui.bloomberg_terminal import BloombergTerminal

async def test():
    app = BloombergTerminal()
    await app.on_mount()
    print('on_mount done')

asyncio.run(test())
print('Done')