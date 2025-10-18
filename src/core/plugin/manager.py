import asyncio
import logging
import importlib
import inspect
from pathlib import Path
from typing import Dict, Any, List, Optional, Type, Set
from .base import Plugin
from .types import PluginEvent, PluginEventType, PluginNodeType, PluginPriority
from discovery.registry import ServiceRegistry


class PluginManager:
    """插件管理器"""
    
    def __init__(self, worker_id: Any, config: Dict, node_type: PluginNodeType, registry):
        self.worker_id = worker_id
        self.config = config
        self.node_type = node_type
        self.registry: ServiceRegistry = registry
        self.logger = logging.getLogger(f"[{self.worker_id}] PluginManager")
        self.plugins: Dict[str, Plugin] = {}
        self.event_subscribers: Dict[PluginEventType, List[Plugin]] = {}
        self.plugin_dirs: List[Path] = []
        self._initialized = False
    
    async def initialize(self):
        """初始化插件管理器"""
        if self._initialized:
            return
        
        # 设置插件目录
        self._setup_plugin_dirs()
        
        # 加载所有插件
        await self.load_all_plugins()
        
        # 初始化事件订阅系统
        self._setup_event_subscriptions()
        
        # 发送节点启动事件
        await self.emit_event(PluginEvent(
            PluginEventType.NODE_START,
            self,
            {'node_type': self.node_type}
        ))
        
        self._initialized = True
    
    def _setup_plugin_dirs(self):
        """设置插件目录"""
        # 从配置获取插件目录
        plugin_dirs_config = self.config.get('plugins', {}).get('directories', [])
        
        # 添加默认插件目录
        default_dirs = [
            Path("plugins/core"),
            Path("plugins/custom")
        ]
        
        # 合并目录列表
        all_dirs = default_dirs + [Path(d) for d in plugin_dirs_config]
        
        # 确保目录存在
        for dir_path in all_dirs:
            if not dir_path.exists():
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    self.logger.info(f"创建插件目录: {dir_path}")
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.logger.error(f"插件目录创建失败 {dir_path}: {e}")
                    continue
            
            if dir_path not in self.plugin_dirs:
                self.plugin_dirs.append(dir_path)
    
    def _setup_event_subscriptions(self):
        """设置事件订阅系统"""
        # 初始化事件订阅字典
        for event_type in PluginEventType:
            self.event_subscribers[event_type] = []
        
        # 根据优先级排序插件
        sorted_plugins = sorted(
            self.plugins.values(),
            key=lambda p: p.priority.value,
            reverse=True  # 优先级高的先执行
        )
        
        # 订阅事件
        for plugin in sorted_plugins:
            for event_type in plugin._event_handlers.keys():
                if event_type in self.event_subscribers:
                    self.event_subscribers[event_type].append(plugin)
    
    async def load_all_plugins(self):
        """加载所有插件（过滤不支持当前节点类型的插件）"""

        for plugin_dir in self.plugin_dirs:
            await self.load_plugins_from_dir(plugin_dir)
    
    async def load_plugins_from_dir(self, plugin_dir: Path):
        """从目录加载插件（过滤不支持当前节点类型的插件）"""
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            self.logger.warning(f"插件目录不存在: {plugin_dir}")
            return
        
        # 遍历目录中的Python文件
        for file_path in plugin_dir.glob("*.py"):
            if file_path.name == "__init__.py":
                continue
            
            try:
                plugin_classes = self._load_plugins_from_file(file_path)
                
                for plugin_class in plugin_classes:
                    # 检查插件是否支持当前节点类型
                    supported_types = getattr(plugin_class, 'PLUGIN_NODE_TYPES', [PluginNodeType.ALL])
                    if self.node_type not in supported_types and PluginNodeType.ALL not in supported_types:
                        self.logger.debug(f"跳过插件 {plugin_class.__name__} - 当前工作模式不支持 {self.node_type.value}")
                        continue
                    
                    await self.register_plugin(plugin_class, file_path.stem)
                    
            except Exception as e:
                self.logger.error(f"加载插件出错 {file_path}: {e}")
                import traceback
                traceback.print_exc()

    def _load_plugins_from_file(self, file_path: Path) -> List[Type[Plugin]]:
        """从文件加载插件类"""
        # 生成模块名
        if file_path.parent.name == "core":
            module_name = f"plugins.core.{file_path.stem}"
        else:
            module_name = f"plugins.custom.{file_path.stem}"
        
        try:
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 查找插件类
            plugin_classes = []
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    issubclass(obj, Plugin) and 
                    obj != Plugin):
                    plugin_classes.append(obj)
            
            return plugin_classes
            
        except Exception as e:
            self.logger.error(f"加载插件出错 {file_path}: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    async def register_plugin(self, plugin_class: Type[Plugin], module_name: str):
        """注册插件（发送加载事件）"""
        plugin_id = f"{module_name}.{plugin_class.__name__}"
        
        if plugin_id in self.plugins:
            self.logger.warning(f"插件 {plugin_id} 已注册")
            return
        
        plugin_config = self.config.get('plugins', {}).get(plugin_id, {})
        
        try:
            # 创建插件实例
            plugin = plugin_class(self.worker_id, plugin_id, plugin_config, self)
            
            # 发送插件加载事件
            load_event = PluginEvent(
                PluginEventType.PLUGIN_LOAD,
                plugin,
                {'config': plugin_config}
            )
            await plugin.handle_event(load_event)
            
            # 注册插件
            self.plugins[plugin_id] = plugin
            
            # 发送插件初始化事件
            init_event = PluginEvent(
                PluginEventType.PLUGIN_INIT,
                plugin
            )
            await plugin.handle_event(init_event)
            
            # 如果配置中启用，则启用插件
            if plugin_config.get('enabled', True):
                enable_event = PluginEvent(
                    PluginEventType.PLUGIN_ENABLE,
                    plugin
                )
                await plugin.handle_event(enable_event)
            
            self.logger.info(f"已注册插件: {plugin.PLUGIN_NAME} v{plugin.PLUGIN_VERSION}")
            
        except Exception as e:
            self.logger.error(f"注册插件时出错 {plugin_id}: {e}")
            import traceback
            traceback.print_exc()
            # 发送插件错误事件
            error_event = PluginEvent(
                PluginEventType.PLUGIN_ERROR,
                None,
                {'plugin_id': plugin_id, 'error': str(e)}
            )
            await self.emit_event(error_event)
    
    async def emit_event(self, event: PluginEvent) -> List[Any]:
        """发送事件到所有订阅的插件"""
        subscribers = self.event_subscribers.get(event.event_type, [])
        results = []
        
        for plugin in subscribers:
            if not plugin.supports_node_type(self.node_type):
                continue
            
            try:
                plugin_results = await plugin.handle_event(event)
                if plugin_results:
                    results.extend(plugin_results)
            except Exception as e:
                import traceback
                traceback.print_exc()

                self.logger.error(f"处理插件 {plugin.plugin_id} 中的事件 {event.event_type} 时出错: {e}")
                # 发送错误事件
                error_event = PluginEvent(
                    PluginEventType.PLUGIN_ERROR,
                    plugin,
                    {'error': str(e), 'original_event': event}
                )
                await self.emit_event(error_event)
        
        return results
    
    async def unregister_plugin(self, plugin_id: str):
        """注销插件（发送卸载事件）"""
        if plugin_id not in self.plugins:
            self.logger.warning(f"未找到插件 {plugin_id}")
            return
        
        plugin = self.plugins[plugin_id]
        
        try:
            # 发送插件禁用事件
            if plugin.is_enabled():
                disable_event = PluginEvent(
                    PluginEventType.PLUGIN_DISABLE,
                    plugin
                )
                await plugin.handle_event(disable_event)
            
            # 发送插件卸载事件
            unload_event = PluginEvent(
                PluginEventType.PLUGIN_UNLOAD,
                plugin
            )
            await plugin.handle_event(unload_event)
            
            # 从插件列表移除
            del self.plugins[plugin_id]
            
            # 从事件订阅中移除
            for event_type, subscribers in self.event_subscribers.items():
                if plugin in subscribers:
                    subscribers.remove(plugin)
            
            self.logger.info(f"插件已卸载: {plugin.PLUGIN_NAME}")
            
        except Exception as e:
            import traceback
            traceback.print_exc()

            self.logger.error(f"卸载插件 {plugin_id} 时出错: {e}")
            # 发送插件错误事件
            error_event = PluginEvent(
                PluginEventType.PLUGIN_ERROR,
                plugin,
                {'error': str(e)}
            )
            await self.emit_event(error_event)
    
    async def enable_plugin(self, plugin_id: str):
        """启用插件（发送启用事件）"""
        if plugin_id not in self.plugins:
            self.logger.warning(f"未找到插件 {plugin_id}")
            return False
        
        plugin = self.plugins[plugin_id]
        
        try:
            if not plugin.is_enabled():
                enable_event = PluginEvent(
                    PluginEventType.PLUGIN_ENABLE,
                    plugin
                )
                await plugin.handle_event(enable_event)
            
            self.logger.info(f"已启用插件: {plugin.PLUGIN_NAME}")
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()

            self.logger.error(f"启用插件 {plugin_id} 时出错: {e}")
            # 发送插件错误事件
            error_event = PluginEvent(
                PluginEventType.PLUGIN_ERROR,
                plugin,
                {'error': str(e)}
            )
            await self.emit_event(error_event)
            return False
    
    async def disable_plugin(self, plugin_id: str):
        """禁用插件（发送禁用事件）"""
        if plugin_id not in self.plugins:
            self.logger.warning(f"未找到插件 {plugin_id}")
            return False
        
        plugin = self.plugins[plugin_id]
        
        try:
            if plugin.is_enabled():
                disable_event = PluginEvent(
                    PluginEventType.PLUGIN_DISABLE,
                    plugin
                )
                await plugin.handle_event(disable_event)
            
            self.logger.info(f"已禁用插件: {plugin.PLUGIN_NAME}")
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()

            self.logger.error(f"禁用插件 {plugin_id} 时出错: {e}")
            # 发送插件错误事件
            error_event = PluginEvent(
                PluginEventType.PLUGIN_ERROR,
                plugin,
                {'error': str(e)}
            )
            await self.emit_event(error_event)
            return False
    
    async def execute_plugin(self, plugin_id: str, context: Dict) -> Any:
        """执行插件"""
        if plugin_id not in self.plugins:
            self.logger.warning(f"未找到插件 {plugin_id}")
            return None
        
        plugin = self.plugins[plugin_id]
        
        if not plugin.is_enabled():
            self.logger.warning(f"插件 {plugin_id} 已禁用")
            return None
        
        try:
            result = await plugin.execute(context)
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()

            self.logger.error(f"执行插件 {plugin_id} 时出错: {e}")
            return None
    
    async def execute_action_plugins(self, action_type: str, context: Dict) -> List[Any]:
        """执行处理特定动作的插件"""
        results = []
        for plugin_id, plugin in self.plugins.items():
            if (hasattr(plugin, 'ACTION_TYPE') and
                plugin.ACTION_TYPE == action_type and
                plugin.is_enabled()):
                try:
                    results.append(await plugin.execute(context))
                except Exception as e:
                    import traceback
                    traceback.print_exc()

                    self.logger.error(f"执行插件 {plugin_id} 的操作时出错: {e}")
        
        return results
    
    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """获取插件"""
        return self.plugins.get(plugin_id)
    
    def get_plugins(self) -> List[Plugin]:
        """获取所有插件"""
        return list(self.plugins.values())
    
    def get_plugin_info(self, plugin_id: str) -> Optional[Dict]:
        """获取插件信息"""
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            return None
        
        return {
            'id': plugin.plugin_id,
            'name': plugin.PLUGIN_NAME,
            'version': plugin.PLUGIN_VERSION,
            'description': plugin.PLUGIN_DESCRIPTION,
            'author': plugin.PLUGIN_AUTHOR,
            'enabled': plugin.is_enabled(),
            'initialized': plugin.is_initialized(),
            'node_types': plugin.PLUGIN_NODE_TYPES,
            'priority': plugin.priority.value
        }
    
    def list_plugins(self) -> List[str]:
        """列出所有插件ID"""
        return list(self.plugins.keys())
    
    async def shutdown(self):
        """关闭插件管理器"""
        if not self._initialized:
            return
        
        self.logger.info("关闭插件管理器")
        
        # 发送节点关闭事件
        shutdown_event = PluginEvent(
            PluginEventType.NODE_SHUTDOWN,
            self,
            {'node_type': self.node_type}
        )
        await self.emit_event(shutdown_event)
        
        # 卸载所有插件
        for plugin_id in list(self.plugins.keys()):
            await self.unregister_plugin(plugin_id)
        
        self._initialized = False
        self.logger.debug("插件管理器已关闭")
