from app.services.observability.metrics import init_metrics, get_metrics
print('Testing metrics initialization...')
metrics = init_metrics('test', '1.0.0')
print('Metrics initialized OK')
print('app_info:', metrics.app_info)
print('http_requests_total:', metrics.http_requests_total)
print('Test passed!')