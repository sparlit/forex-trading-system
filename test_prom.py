import time
from src.monitoring.prometheus_client import init_metrics
init_metrics(port=9090)
print('prometheus started')
time.sleep(30)