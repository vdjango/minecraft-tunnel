import asyncio
import logging
import time
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field

from discovery.models import NodeInfo
from loadbalancer.manager import LoadBalancerManager

class ServiceRegistry(LoadBalancerManager):
    """服务注册中心"""
    
    def __init__(self, config: Dict):
        super(ServiceRegistry, self).__init__(config)
        self.config = config
        
        self.heartbeat_interval = int(config.get('discovery').get('heartbeat_interval', 30))
        self.heartbeat_timeout = int(config.get('discovery').get('heartbeat_timeout', 90))
        self.logger = logging.getLogger("ServiceRegistry")

    async def start(self):
        """启动注册中心"""
        self.logger.info("Starting service registry")
        
        # 启动心跳检查任务
        asyncio.create_task(self._heartbeat_check_loop())
        
        # 注册当前节点
        await self.register_node(self._get_current_node_info())
    
    async def stop(self):
        """停止注册中心"""
        self.logger.info("Stopping service registry")
        # 注销当前节点
        await self.unregister_node(self.config.get('node').get('node_id', 'default'))
    
    async def register_node(self, node_info: NodeInfo):
        """注册节点"""
        self.nodes[node_info.node_id] = node_info
        return True
    
    async def unregister_node(self, node_id: str):
        """注销节点"""
        if node_id in self.nodes:
            del self.nodes[node_id]
    
    async def get_node(self, node_id) -> NodeInfo:
        """获取可用节点列表"""
        return self.nodes.get(node_id, None)
    
    async def get_available_nodes(self, node_type: str = None) -> List[NodeInfo]:
        """获取可用节点列表"""
        now = time.time()
        available_nodes = []
        
        for node in self.nodes.values():
            if (node.is_active and 
                (now - node.last_heartbeat) < self.heartbeat_timeout):
                if node_type is None or node.node_type == node_type:
                    available_nodes.append(node)
        
        # 按负载排序（低负载优先）
        available_nodes.sort(key=lambda x: x.load)
        return available_nodes
    
    async def update_node_status(self, node_id: str, status: Dict[str, Any]):
        """更新节点状态"""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.load = status.get('load', 0.0)
            node.last_heartbeat = time.time()
            self.logger.debug(f"Updated status for node {node_id}")
    
    async def _heartbeat_check_loop(self):
        """心跳检查循环"""
        while True:
            try:
                await self._check_heartbeats()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                import traceback
                traceback.print_exc()

                self.logger.error(f"Heartbeat check error: {e}")
    
    async def _check_heartbeats(self):
        """检查心跳"""
        now = time.time()
        for node_id, node in self.nodes.items():
            if (now - node.last_heartbeat) > self.heartbeat_timeout:
                node.is_active = False
                self.logger.warning(f"Node {node_id} heartbeat timeout")
    
    def _get_current_node_info(self) -> NodeInfo:
        """获取当前节点信息"""
        return NodeInfo(
            node_id=self.config.get('node').get('node_id', 'default'),
            host=self.config.get('server').get('host', '0.0.0.0'),
            port=self.config.get('server').get('port', 8080),
            node_type=self.config.get('node').get('node_type', 'worker'),
            load=0.0,
            last_heartbeat=time.time()
        )

    async def health_check(self) -> Dict:
        """健康检查 - 完整实现"""
        try:
            now = time.time()
            active_nodes = len([n for n in self.nodes.values() if n.is_active])
            total_nodes = len(self.nodes)
            
            # 计算节点健康度
            health_score = active_nodes / total_nodes if total_nodes > 0 else 0
            
            # 确定整体状态
            if health_score >= 0.8:
                status = 'healthy'
            elif health_score >= 0.5:
                status = 'degraded'
            else:
                status = 'unhealthy'
            
            # 检查各个节点的详细状态
            node_details = {}
            for node_id, node in self.nodes.items():
                node_health = 'healthy' if node.is_active else 'unhealthy'
                time_since_heartbeat = now - node.last_heartbeat
                
                node_details[node_id] = {
                    'status': node_health,
                    'load': node.load,
                    'time_since_heartbeat': time_since_heartbeat,
                    'node_type': node.node_type
                }
            
            health_result = {
                'status': status,
                'health_score': health_score,
                'active_nodes': active_nodes,
                'total_nodes': total_nodes,
                'node_details': node_details,
                'timestamp': now,
                'registry_uptime': now - self.start_time if hasattr(self, 'start_time') else 0
            }
            
            # 记录本次健康检查
            self.logger.info(f"Health check completed: {status} (score: {health_score:.2f})")
            
            return health_result
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            self.logger.error(f"Health check failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': time.time()
            }
