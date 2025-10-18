import logging
import time
from typing import List, Dict, Any, Optional
from multiprocessing import Manager
from .strategies import LoadBalancingStrategy, RoundRobinStrategy, LeastConnectionsStrategy
from discovery.registry import NodeInfo


class LoadBalancerManager:
    """负载均衡管理器（支持多进程共享）"""
    
    def __init__(self, config: Dict[str, Any], manager: Optional[Manager] = None):
        self.config = config
        self.strategy_name = config.get('strategy', 'round_robin')
        self.strategy: Optional[LoadBalancingStrategy] = None
        self.logger = logging.getLogger("LoadBalancer")
        
        # 使用多进程管理器创建共享数据结构
        self.manager = manager or Manager()
        self.nodes: Dict[str, NodeInfo] = self.manager.dict()  # 共享节点字典
        self.node_lock = self.manager.Lock()  # 共享锁

        # 初始化策略
        if self.strategy_name == 'round_robin':
            self.strategy = RoundRobinStrategy()
        elif self.strategy_name == 'least_connections':
            self.strategy = LeastConnectionsStrategy()
        else:
            self.logger.warning(f"Unknown strategy '{self.strategy_name}', using round_robin")
            self.strategy = RoundRobinStrategy()
        
        self.logger.info(f"已设置负载均衡策略为 {self.strategy_name}")
    
    def update_nodes(self, nodes: List[Dict[str, Any]]):
        """更新节点列表（线程安全）"""
        with self.node_lock:
            # 清空现有节点
            self.nodes.clear()
            
            # 添加新节点
            for node in nodes:
                node_id = node.get('id')
                if node_id:
                    self.nodes[node_id] = node
            
            self.logger.info(f"已更新节点列表，当前有 {len(self.nodes)} 个节点")
    
    def add_node(self, node: Dict[str, Any]):
        """添加单个节点（线程安全）"""
        with self.node_lock:
            node_id = node.get('id')
            if node_id:
                self.nodes[node_id] = node
                self.logger.info(f"已添加节点: {node_id}")
    
    def remove_node(self, node_id: str):
        """移除单个节点（线程安全）"""
        with self.node_lock:
            if node_id in self.nodes:
                del self.nodes[node_id]
                self.logger.info(f"已移除节点: {node_id}")
    
    def update_node_status(self, node_id: str, status: str, current_load: int = None):
        """更新节点状态（线程安全）"""
        with self.node_lock:
            if node_id in self.nodes:
                self.nodes[node_id]['status'] = status
                if current_load is not None:
                    self.nodes[node_id]['current_load'] = current_load
                self.logger.debug(f"已更新节点状态: {node_id} -> {status}")
    
    async def select_node(self) -> Optional[Dict[str, Any]]:
        """选择节点"""
        if not self.nodes:
            self.logger.error("未发现可用节点")
            return None
        
        active_nodes = [node for node in self.nodes.values() if node.is_active]  #  and node.node_type == 'worker'
        if not active_nodes:
            self.logger.error("未发现可用节点")
            return None
        
        return await self.strategy.select(active_nodes)
    

    async def select_nodex(self) -> Optional[Dict[str, Any]]:
        """选择节点（线程安全）"""
        with self.node_lock:
            if not self.nodes:
                self.logger.error("未发现可用节点")
                return None
            
            # 获取活跃节点
            active_nodes = []
            for node_id, node_info in self.nodes.items():
                if node_info == 'active' and node_info.get('node_type') == 'worker':
                    active_nodes.append(node_info)
            
            if not active_nodes:
                self.logger.error("未发现可用节点")
                return None
            
            # 使用策略选择节点
            return await self.strategy.select(active_nodes)
    
    def report_connection(self, node_id: str, delta: int = 1):
        """报告连接变化（线程安全）"""
        with self.node_lock:
            if node_id in self.nodes:
                current_connections = self.nodes[node_id].get('connections', 0)
                self.nodes[node_id]['connections'] = current_connections + delta
                self.logger.debug(f"节点 {node_id} 连接数变化: {delta}, 当前: {current_connections + delta}")
            else:
                self.logger.warning(f"节点 {node_id} 不存在，无法更新连接数")
    
    def get_node_info(self, node_id: str) -> Optional[Dict[str, Any]]:
        """获取节点信息（线程安全）"""
        with self.node_lock:
            return self.nodes.get(node_id)
    
    def get_all_nodes(self) -> Dict[str, Any]:
        """获取所有节点信息（线程安全）"""
        with self.node_lock:
            return dict(self.nodes)  # 返回副本，避免直接操作共享数据
    
    def get_active_nodes(self) -> List[Dict[str, Any]]:
        """获取活跃节点列表（线程安全）"""
        with self.node_lock:
            active_nodes = []
            for node_id, node_info in self.nodes.items():
                if node_info.get('status') == 'active':
                    active_nodes.append(node_info)
            return active_nodes
    
    async def health_check(self) -> Dict:
        """负载均衡器健康检查（线程安全）"""
        with self.node_lock:
            try:
                active_nodes = len([n for n in self.nodes.values() if n.get('status') == 'active'])
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
                import traceback
                traceback.print_exc()
                
                return {
                    'status': 'error',
                    'error': str(e),
                    'timestamp': time.time()
                }
    
    def cleanup(self):
        """清理资源"""
        if hasattr(self, 'manager'):
            self.manager.shutdown()

