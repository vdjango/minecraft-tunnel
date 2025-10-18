import asyncio
import logging
import time
from typing import Dict, Optional

from core.plugin.base import Plugin
from core.plugin.types import PluginEvent, PluginEventType, PluginPriority


class ConnectionMonitorPlugin(Plugin):
    """连接监控插件（基于心跳事件驱动）"""
    
    PLUGIN_NAME = "连接监控插件"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "基于心跳事件监控连接状态"
    PLUGIN_AUTHOR = "系统"
    PLUGIN_PRIORITY = PluginPriority.CRITICAL
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger("ConnectionMonitor")
        
        # 连接状态跟踪
        self.connections = {}  # connection_id -> connection_info
        self.last_heartbeat = {}  # connection_id -> last_heartbeat_time
        
        # 配置参数
        self.heartbeat_timeout = kwargs.get('heartbeat_timeout', 300)  # 5分钟超时
        self.state_timeout = kwargs.get('state_timeout', 60)  # 1分钟状态超时
        self.check_interval = kwargs.get('check_interval', 30)  # 30秒检查间隔
        
        # 注册事件处理器
        self.register_handler(PluginEventType.HEARTBEAT, self.handle_heartbeat)
        self.register_handler(PluginEventType.CONNECTION_ACCEPTED, self.handle_connection_accepted)
        self.register_handler(PluginEventType.CONNECTION_CLOSED, self.handle_connection_closed)
        self.register_handler(PluginEventType.CONNECTION_READY, self.handle_connection_ready)
        self.register_handler(PluginEventType.CONNECTION_ERROR, self.handle_connection_error)
        
        # 启动监控任务
        self.monitor_task = None
    
    async def on_enable(self, event: PluginEvent):
        """插件启用时启动监控任务"""
        self.logger.info("连接监控插件已启用")
        self.monitor_task = asyncio.create_task(self._monitor_connections())
    
    async def on_disable(self, event: PluginEvent):
        """插件禁用时停止监控任务"""
        self.logger.info("连接监控插件已禁用")
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
    
    async def handle_heartbeat(self, event: PluginEvent):
        """处理心跳事件"""
        try:
            event_data = event.data
            connection_id = event_data.get('connection_id')
            timestamp = event_data.get('timestamp')
            
            if connection_id:
                # 更新最后心跳时间
                self.last_heartbeat[connection_id] = timestamp
                
                # 更新连接活动状态
                if connection_id in self.connections:
                    self.connections[connection_id]['last_activity'] = timestamp
                    self.connections[connection_id]['active'] = True
                
                self.logger.debug(f"收到心跳: {connection_id}")
                
        except Exception as e:
            self.logger.error(f"处理心跳事件错误: {e}")
    
    async def handle_connection_accepted(self, event: PluginEvent):
        """处理连接接受事件"""
        try:
            event_data = event.data
            connection_id = event_data.get('connection_id')
            client_addr = event_data.get('client_addr')
            
            if connection_id:
                # 添加新连接
                self.connections[connection_id] = {
                    'id': connection_id,
                    'client_addr': client_addr,
                    'state': 'connecting',
                    'last_activity': time.time(),
                    'active': True,
                    'created_at': time.time()
                }
                
                self.logger.info(f"开始监控新连接: {connection_id}")
                
        except Exception as e:
            self.logger.error(f"处理连接接受事件错误: {e}")
    
    async def handle_connection_closed(self, event: PluginEvent):
        """处理连接关闭事件"""
        try:
            event_data = event.data
            connection_id = event_data.get('connection_id')
            reason = event_data.get('reason', 'unknown')
            
            if connection_id and connection_id in self.connections:
                # 移除连接
                del self.connections[connection_id]
                if connection_id in self.last_heartbeat:
                    del self.last_heartbeat[connection_id]
                
                self.logger.info(f"停止监控连接: {connection_id}, 原因: {reason}")
                
        except Exception as e:
            self.logger.error(f"处理连接关闭事件错误: {e}")
    
    async def handle_connection_ready(self, event: PluginEvent):
        """处理连接就绪事件"""
        try:
            event_data = event.data
            connection_id = event_data.get('connection_id')
            
            if connection_id and connection_id in self.connections:
                # 更新连接状态
                self.connections[connection_id]['state'] = 'ready'
                self.connections[connection_id]['last_activity'] = time.time()
                
                self.logger.debug(f"连接就绪: {connection_id}")
                
        except Exception as e:
            self.logger.error(f"处理连接就绪事件错误: {e}")
    
    async def handle_connection_error(self, event: PluginEvent):
        """处理连接错误事件"""
        try:
            event_data = event.data
            connection_id = event_data.get('connection_id')
            error = event_data.get('error', 'unknown')
            
            if connection_id and connection_id in self.connections:
                # 更新连接状态
                self.connections[connection_id]['state'] = 'error'
                self.connections[connection_id]['last_activity'] = time.time()
                self.connections[connection_id]['error'] = error
                
                self.logger.warning(f"连接错误: {connection_id}, 错误: {error}")
                
        except Exception as e:
            self.logger.error(f"处理连接错误事件错误: {e}")
    
    async def _monitor_connections(self):
        """监控连接状态（基于心跳事件）"""
        while True:
            try:
                # 检查所有连接的活动状态
                inactive_connections = []
                current_time = time.time()
                
                for connection_id, connection_info in list(self.connections.items()):
                    last_activity = connection_info.get('last_activity', 0)
                    state = connection_info.get('state', 'unknown')
                    
                    # 检查连接是否超时（无心跳）
                    if current_time - last_activity > self.heartbeat_timeout:
                        self.logger.warning(f"连接超时: {connection_id}, 最后活动: {last_activity}")
                        inactive_connections.append((connection_id, "心跳超时"))
                    
                    # 检查连接是否长时间处于非就绪状态
                    elif (state != 'ready' and 
                          current_time - last_activity > self.state_timeout):
                        self.logger.warning(f"连接卡滞 {state}: {connection_id}")
                        inactive_connections.append((connection_id, f"状态卡滞: {state}"))
                
                # 处理不活跃的连接
                for connection_id, reason in inactive_connections:
                    self.logger.info(f"标记不活跃连接: {connection_id}, 原因: {reason}")
                    
                    # 发送连接超时事件
                    await self.plugin_manager.emit_event(PluginEvent(
                        PluginEventType.CONNECTION_TIMEOUT,
                        self,
                        {
                            'connection_id': connection_id,
                            'reason': reason,
                            'last_activity': self.connections[connection_id].get('last_activity'),
                            'timeout_duration': current_time - self.connections[connection_id].get('last_activity', current_time)
                        }
                    ))
                
                # 记录连接统计
                active_count = len([c for c in self.connections.values() if c.get('active', False)])
                ready_count = len([c for c in self.connections.values() if c.get('state') == 'ready'])
                total_count = len(self.connections)
                
                self.logger.debug(f"连接统计: {active_count} 活跃, {ready_count} 就绪, {total_count} 总计")
                
                # 等待下一次检查
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"连接监控出错: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(10)  # 出错时等待10秒
    
    async def get_connection_stats(self) -> Dict:
        """获取连接统计信息"""
        active_count = len([c for c in self.connections.values() if c.get('active', False)])
        ready_count = len([c for c in self.connections.values() if c.get('state') == 'ready'])
        error_count = len([c for c in self.connections.values() if c.get('state') == 'error'])
        timeout_count = len([c for c in self.connections.values() 
                           if time.time() - c.get('last_activity', 0) > self.heartbeat_timeout])
        
        return {
            'total_connections': len(self.connections),
            'active_connections': active_count,
            'ready_connections': ready_count,
            'error_connections': error_count,
            'timeout_connections': timeout_count,
            'timestamp': time.time()
        }
    
    async def get_connection_info(self, connection_id: str) -> Optional[Dict]:
        """获取连接详细信息"""
        return self.connections.get(connection_id)
    
    async def get_all_connections(self) -> Dict[str, Dict]:
        """获取所有连接信息"""
        return dict(self.connections)
