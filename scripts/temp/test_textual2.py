import asyncio
from textual.app import App
from textual.widgets import DataTable, Static
from textual.containers import Horizontal, Vertical

class TestApp(App):
    def compose(self):
        with Horizontal():
            yield Static('Left panel')
            with Vertical():
                yield DataTable(id='test-table')
    
    async def on_mount(self):
        print('on_mount called', flush=True)
        table = self.query_one('#test-table', DataTable)
        print(f'Table: {table}', flush=True)
        table.add_columns('Symbol', 'Bid', 'Ask')
        table.add_row('TEST', '1.000', '1.001')
        print(f'Row count: {table.row_count}', flush=True)
        await asyncio.sleep(2)
        self.exit()

if __name__ == '__main__':
    asyncio.run(TestApp().run_async())