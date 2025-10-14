import time

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class LoadBalancingStrategy(ABC):
    """负载均衡策略基类"""
    
    @abstractmethod
    def select(self, nodes: List[Dict[str, Any]], client_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """选择节点"""
        pass


class RoundRobinStrategy(LoadBalancingStrategy):
    """轮询策略"""
    
    def __init__(self):
        self.current_index = -1
    
    def select(self, nodes: List[Dict[str, Any]], client_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """选择节点"""
        self.current_index = (self.current_index + 1) % len(nodes)
        return nodes[self.current_index]

class LeastConnectionsStrategy(LoadBalancingStrategy):
    """最少连接策略"""
    
    def select(self, nodes: List[Dict[str, Any]], client_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """选择节点"""
        # 按连接数排序，选择连接数最少的节点
        sorted_nodes = sorted(nodes, key=lambda x: x.get('connections', 0))
        return sorted_nodes[0]

class WeightedRoundRobinStrategy(LoadBalancingStrategy):
    """加权轮询策略"""
    
    def __init__(self):
        self.current_index = -1
        self.current_weight = 0
    
    def select(self, nodes: List[Dict[str, Any]], client_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """选择节点"""
        max_weight = max(node.get('weight', 1) for node in nodes)
        total_nodes = len(nodes)
        
        while True:
            self.current_index = (self.current_index + 1) % total_nodes
            if self.current_index == 0:
                self.current_weight = self.current_weight - 1
                if self.current_weight <= 0:
                    self.current_weight = max_weight
            
            node = nodes[self.current_index]
            if node.get('weight', 1) >= self.current_weight:
                return node

class LatencyBasedStrategy(LoadBalancingStrategy):
    """基于延迟的策略"""
    
    def select(self, nodes: List[Dict[str, Any]], client_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """选择节点"""
        # 这里简化实现，实际应用中需要测量延迟
        # 按延迟排序，选择延迟最低的节点
        sorted_nodes = sorted(nodes, key=lambda x: x.get('latency', 0))
        return sorted_nodes[0]
