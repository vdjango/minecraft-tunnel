import logging
import time
from typing import List, Dict, Any, Optional
from .strategies import LoadBalancingStrategy, RoundRobinStrategy, LeastConnectionsStrategy

class LoadBalancerManager:
    """负载均衡管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.strategy_name = config.get('strategy', 'round_robin')
        self.strategy: Optional[LoadBalancingStrategy] = None
        self.nodes: List[Dict[str, Any]] = []
        self.logger = logging.getLogger("LoadBalancer")
    
    async def start(self):
        """启动负载均衡管理器"""
        self.logger.info("Starting load balancer")
        
        # 初始化策略
        if self.strategy_name == 'round_robin':
            self.strategy = RoundRobinStrategy()
        elif self.strategy_name == 'least_connections':
            self.strategy = LeastConnectionsStrategy()
        else:
            self.logger.warning(f"Unknown strategy '{self.strategy_name}', using round_robin")
            self.strategy = RoundRobinStrategy()
        
        # 初始节点列表（实际应用中应从服务发现获取）
        self.nodes = [
            {'id': 'node1', 'host': '127.0.0.1', 'port': 8080, 'connections': 0, 'status': 'active'},
            {'id': 'node2', 'host': '127.0.0.1', 'port': 8081, 'connections': 0, 'status': 'active'}
        ]
        
        self.logger.info(f"Using {self.strategy_name} strategy with {len(self.nodes)} nodes")
    
    async def stop(self):
        """停止负载均衡管理器"""
        self.logger.info("Stopping load balancer")
    
    def update_nodes(self, nodes: List[Dict[str, Any]]):
        """更新节点列表"""
        self.nodes = nodes
        self.logger.info(f"Updated node list, now {len(self.nodes)} nodes")
    
    def select_node(self, client_info: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """选择节点"""
        if not self.nodes:
            self.logger.error("No nodes available for load balancing")
            return None
        
        active_nodes = [node for node in self.nodes if node.get('status') == 'active']
        if not active_nodes:
            self.logger.error("No active nodes available")
            return None
        
        return self.strategy.select(active_nodes, client_info)
    
    def report_connection(self, node_id: str, delta: int = 1):
        """报告连接变化"""
        for node in self.nodes:
            if node['id'] == node_id:
                node['connections'] += delta
                return
        self.logger.warning(f"Node {node_id} not found for connection report")

    async def health_check(self) -> Dict:
        """负载均衡器健康检查"""
        try:
            active_nodes = len([n for n in self.nodes if n.get('status') == 'active'])
            total_nodes = len(self.nodes)
            
            # 计算负载均衡器健康度
            health_score = active_nodes / total_nodes if total_nodes > 0 else 0
            
            return {
                'status': 'healthy' if health_score > 0 else 'unhealthy',
                'health_score': health_score,
                'active_nodes': active_nodes,
                'total_nodes': total_nodes,
                'strategy': self.strategy_name,
                'timestamp': time.time()
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': time.time()
            }
