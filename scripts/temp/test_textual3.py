import asyncio
import sys
print('Starting...', file=sys.stderr, flush=True)
from textual.app import App
from textual.widgets import DataTable, Static
from textual.containers import Horizontal

class TestApp(App):
    CSS = '''
    Screen {
        layout: horizontal;
    }
    '''
    def compose(self):
        with Horizontal():
            yield Static('Left panel')
            yield DataTable(id='test-table')
    
    async def on_mount(self):
        print('on_mount called', file=sys.stderr, flush=True)
        table = self.query_one('#test-table', DataTable)
        print(f'Table: {table}', file=sys.stderr, flush=True)
        table.add_columns('Symbol', 'Bid', 'Ask')
        table.add_row('TEST', '1.000', '1.001')
        print(f'Row count: {table.row_count}', file=sys.stderr, flush=True)
        await asyncio.sleep(1)
        self.exit()

if __name__ == '__main__':
    asyncio.run(TestApp().run_async())
    print('Done', file=sys.stderr, flush=True)