import asyncio
from textual.app import App
from textual.widgets import DataTable

class TestApp(App):
    def compose(self):
        yield DataTable(id='test-table')
    
    def on_mount(self):
        table = self.query_one('#test-table', DataTable)
        table.add_columns('Symbol', 'Bid', 'Ask')
        table.add_row('TEST', '1.000', '1.001')
        print(f'Row count: {table.row_count}')
        self.exit()

if __name__ == '__main__':
    asyncio.run(TestApp().run_async())