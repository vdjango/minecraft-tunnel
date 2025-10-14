import time
from collections import defaultdict
from typing import Dict, Any, List, Tuple

class MetricsCollector:
    """监控指标收集器"""
    
    def __init__(self):
        self.metrics = {
            'connections': 0,
            'bytes_received': 0,
            'bytes_sent': 0,
            'start_time': time.time(),
            'errors': 0,
            'active_sessions': 0,
            'peak_connections': 0,
            'heartbeats': 0
        }
        self.custom_metrics = defaultdict(int)
        self.historical = {
            'connections': [],
            'throughput': [],
            'health_status': []  # 添加健康状态历史记录
        }
        self.health_status = {
            'overall': 'healthy',
            'last_check': time.time(),
            'details': {}
        }
    
    def increment(self, metric: str, value: int = 1):
        """增加指标值"""
        if metric in self.metrics:
            self.metrics[metric] += value
        else:
            self.custom_metrics[metric] += value
        
        # 更新峰值连接数
        if metric == 'connections':
            if self.metrics['connections'] > self.metrics['peak_connections']:
                self.metrics['peak_connections'] = self.metrics['connections']
    
    def record(self, metric: str, value: Any):
        """记录指标值"""
        if metric in self.metrics:
            self.metrics[metric] = value
        else:
            self.custom_metrics[metric] = value
    
    def add_historical(self, metric: str, value: Any):
        """添加历史记录"""
        if metric in self.historical:
            self.historical[metric].append((time.time(), value))
            # 保留最近100条记录
            if len(self.historical[metric]) > 100:
                self.historical[metric].pop(0)
    
    def collect(self) -> Dict[str, Any]:
        """收集当前指标"""
        uptime = time.time() - self.metrics['start_time']
        return {
            **self.metrics,
            **self.custom_metrics,
            'uptime': uptime,
            'historical': self.historical
        }
    
    def get_throughput(self) -> Tuple[float, float]:
        """计算吞吐量 (bytes/s)"""
        if len(self.historical['throughput']) < 2:
            return 0.0, 0.0
        
        # 计算最近两次记录之间的吞吐量
        last_time, last_bytes = self.historical['throughput'][-1]
        prev_time, prev_bytes = self.historical['throughput'][-2]
        
        time_diff = last_time - prev_time
        bytes_diff = last_bytes - prev_bytes
        
        if time_diff <= 0:
            return 0.0, 0.0
        
        return bytes_diff / time_diff, time_diff

    def record_health_status(self, health_data: Dict):
        """记录健康状态"""
        current_time = time.time()
        
        # 更新健康状态
        self.health_status = {
            'overall': health_data.get('status', 'unknown'),
            'last_check': current_time,
            'details': health_data
        }
        
        # 记录历史状态
        self.historical['health_status'].append({
            'timestamp': current_time,
            'status': health_data.get('status', 'unknown'),
            'details': health_data
        })
        
        # 保留最近100条记录
        if len(self.historical['health_status']) > 100:
            self.historical['health_status'].pop(0)
        
        # 根据健康状态更新相关指标
        if health_data.get('status') == 'unhealthy':
            self.increment('health_checks_failed')
        else:
            self.increment('health_checks_passed')
    
    def get_health_status(self) -> Dict:
        """获取当前健康状态"""
        return self.health_status
    
    def is_healthy(self) -> bool:
        """检查整体健康状态"""
        return self.health_status.get('overall') == 'healthy'
