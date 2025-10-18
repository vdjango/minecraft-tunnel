import abc
import time
import logging
import inspect
from typing import Dict, Any, List, Optional, Set, Callable, Coroutine

from .types import PluginEvent, PluginEventType, PluginNodeType, PluginPriority
from discovery.registry import ServiceRegistry


class Plugin(abc.ABC):
    """插件基类（修复版）"""
    
    # 插件元数据
    PLUGIN_NAME = "Unnamed Plugin"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "No description provided"
    PLUGIN_AUTHOR = "Unknown"
    PLUGIN_NODE_TYPES = [PluginNodeType.ALL]  # 支持的节点类型
    PLUGIN_PRIORITY = PluginPriority.NORMAL
    PLUGIN_DEPENDENCIES = []  # 依赖的插件ID
    
    def __init__(self, worker_id: Any, plugin_id: str, config: Dict, plugin_manager: Any):
        self.worker_id = worker_id
        self.plugin_id = plugin_id
        self.config = config
        self.plugin_manager = plugin_manager
        self.logger = logging.getLogger(f"[{self.worker_id}] [Plugin] {plugin_id}")
        self._state = "created"  # created -> loaded -> initialized -> enabled -> disabled -> unloaded
        self._event_handlers = {}  # 事件处理器映射
        self._node_type = None  # 当前节点类型
        self._dependencies_met = False  # 依赖是否满足
        
        # 自动注册事件处理器
        self._register_event_handlers()
    
    def _register_event_handlers(self):
        """自动注册事件处理器"""
        methods = inspect.getmembers(self, predicate=inspect.ismethod)
        for name, method in methods:
            if name.startswith('on_') and callable(method):
                # 提取事件类型
                event_name = name[3:].upper()
                try:
                    event_type = PluginEventType[event_name]
                    self.register_handler(event_type, method)
                    # self.logger.info(f"注册事件 {event_name} {event_type}")
                except KeyError:
                    # 不是预定义的事件类型，可能是自定义事件
                    # self.logger.warning(f"不是预定义的事件类型 {event_name} {method}")
                    pass
    
    def register_handler(self, event_type: PluginEventType, handler: Callable):
        """注册事件处理器"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    async def handle_event(self, event: PluginEvent) -> Optional[Any]:
        """高效处理事件（优化版）"""
        handlers = self._event_handlers.get(event.event_type)
        if not handlers:
            return None
        
        results = []
        for handler in handlers:
            try:
                # 执行事件处理器
                result = await handler(event)
                results.append(result)
            except Exception as e:
                # 错误处理 - 只在调试模式下打印完整堆栈
                import traceback
                traceback.print_exc()
                
                # 记录错误日志
                self.logger.error(f"事件处理程序出错 {handler.__name__}: {e}")

        return results

    async def on_load(self, event: PluginEvent):
        """插件加载时调用"""
        self._state = "loaded"
        # self.logger.info(f"加载 {self.PLUGIN_NAME} 插件")
    
    async def on_init(self, event: PluginEvent):
        """插件初始化时调用"""
        # 检查依赖
        if not await self._check_dependencies():
            self.logger.error(f"插件 {self.PLUGIN_NAME} 依赖项未满足")
            raise Exception(f"插件 {self.PLUGIN_NAME} 依赖项未满足")
        
        self._state = "initialized"
        self.logger.info(f"插件 {self.PLUGIN_NAME} 已初始化")
    
    async def on_enable(self, event: PluginEvent):
        """插件启用时调用"""
        self._state = "enabled"
        self.logger.info(f"插件 {self.PLUGIN_NAME} 已启用")
    
    async def on_disable(self, event: PluginEvent):
        """插件禁用时调用"""
        self._state = "disabled"
        self.logger.info(f"插件 {self.PLUGIN_NAME} 已禁用")
    
    async def on_unload(self, event: PluginEvent):
        """插件卸载时调用"""
        self._state = "unloaded"
        self.logger.info(f"插件 {self.PLUGIN_NAME} 已卸载")
    
    async def on_error(self, event: PluginEvent):
        """插件错误时调用"""
        error_data = event.data.get('error', 'Unknown error')
        self.logger.error(f"插件 {self.PLUGIN_NAME} 发生错误: {error_data}")
    
    async def on_node_start(self, event: PluginEvent):
        """节点启动时调用"""
        self._node_type = event.data.get('node_type')
        # self.logger.info(f"节点已启动: {self._node_type}")
    
    async def on_node_ready(self, event: PluginEvent):
        """节点就绪时调用"""
        # self.logger.info("节点已就绪")
        pass
    
    async def on_node_stop(self, event: PluginEvent):
        """节点停止时调用"""
        # self.logger.info("节点正在停止")
        pass
    
    async def on_node_shutdown(self, event: PluginEvent):
        """节点关闭时调用"""
        # self.logger.info("节点正在关闭")
        pass
    
    # 连接事件（新增）
    async def on_connection_accepted(self, event: PluginEvent):
        """连接接受时调用"""  # √
    
    async def on_connection_handshake(self, event: PluginEvent):
        """连接握手时调用"""  # √
    
    async def on_connection_authenticated(self, event: PluginEvent):
        """连接认证时调用"""  # √
    
    async def on_connection_ready(self, event: PluginEvent):
        """连接就绪时调用"""  # √
    
    async def on_connection_data_received(self, event: PluginEvent):
        """数据接收时调用"""  # √

    async def on_connection_data_sent(self, event: PluginEvent):
        """数据发送时调用"""  # √
    
    async def on_connection_closed(self, event: PluginEvent):
        """连接关闭时调用"""  # √
    
    async def on_connection_error(self, event: PluginEvent):
        """连接错误时调用"""  # TODO
        error = event.data.get('error', 'Unknown error')
        connection_id = event.data.get('connection_id', 'unknown')
        self.logger.error(f"连接错误: {connection_id}, 错误: {error}")
    
    # 数据包事件（新增）
    async def on_packet_received(self, event: PluginEvent):
        """数据包接收时调用"""  # √
    
    async def on_packet_processed(self, event: PluginEvent):
        """数据包处理时调用"""  # √
    
    async def on_packet_sent(self, event: PluginEvent):
        """数据包发送时调用"""  # TODO
        packet_data = event.data.get('packet', {})
        packet_type = packet_data.get('packet_type', 0)
        connection_id = packet_data.get('connection_id', 'unknown')
        self.logger.debug(f"数据包已发送: {connection_id}, 类型: {packet_type}")
    
    async def _check_dependencies(self) -> bool:
        """检查插件依赖是否满足"""
        if not self.PLUGIN_DEPENDENCIES:
            self._dependencies_met = True
            return True
        
        for dep_id in self.PLUGIN_DEPENDENCIES:
            dep_plugin = self.plugin_manager.get_plugin(dep_id)
            if not dep_plugin or not dep_plugin.is_initialized():
                self.logger.warning(f"依赖项 {dep_id} 不可用")
                return False
        
        self._dependencies_met = True
        return True
    
    def is_loaded(self) -> bool:
        """检查插件是否已加载"""
        return self._state in ["loaded", "initialized", "enabled", "disabled"]
    
    def is_initialized(self) -> bool:
        """检查插件是否已初始化"""
        return self._state in ["initialized", "enabled", "disabled"]
    
    def is_enabled(self) -> bool:
        """检查插件是否已启用"""
        return True  # self._state == "enabled"
    
    def is_disabled(self) -> bool:
        """检查插件是否已禁用"""
        return self._state == "disabled"
    
    def is_unloaded(self) -> bool:
        """检查插件是否已卸载"""
        return self._state == "unloaded"
    
    def get_state(self) -> str:
        """获取插件状态"""
        return self._state
    
    def supports_node_type(self, node_type: PluginNodeType) -> bool:
        """检查插件是否支持指定节点类型"""
        return PluginNodeType.ALL in self.PLUGIN_NODE_TYPES or node_type in self.PLUGIN_NODE_TYPES
    
    @property
    def priority(self) -> PluginPriority:
        """获取插件优先级"""
        return self.PLUGIN_PRIORITY
    
    async def execute(self, context: Dict) -> Any:
        """执行插件功能"""
        pass


class ActionPlugin(Plugin):
    """动作插件基类，用于处理特定类型的动作"""
    
    def __init__(self, worker_id: Any, plugin_id: str, config: Dict, plugin_manager: Any):
        super().__init__(worker_id, plugin_id, config, plugin_manager)
        self.action_type = getattr(self, 'ACTION_TYPE', None)

    async def execute(self, context: Dict) -> Any:
        """执行插件功能"""
        if not self.is_enabled():
            return None
        
        connection = context.get('connection')
        data = context.get('data')
        
        if not all([connection, data]):
            self.logger.error("缺少操作插件所需的上下文")
            return None
        
        return await self.handle_action(connection, data, context)
