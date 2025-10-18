import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Type
from .base import PluginBase

class PluginLoader:
    """插件加载器"""
    
    def __init__(self):
        self.logger = logging.getLogger("PluginLoader")
        self.loaded_modules = set()
    
    def load_plugins_from_dir(self, plugin_dir: Path) -> List[Type[PluginBase]]:
        """从目录加载插件类"""
        plugin_classes = []
        
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            self.logger.warning(f"Plugin directory does not exist: {plugin_dir}")
            return plugin_classes
        
        # 遍历目录中的Python文件
        for file_path in plugin_dir.glob("*.py"):
            if file_path.name == "__init__.py":
                continue
            
            try:
                classes = self.load_plugins_from_file(file_path)
                plugin_classes.extend(classes)
            except Exception as e:
                self.logger.error(f"Error loading plugins from {file_path}: {e}")
                import traceback
                traceback.print_exc()
        
        return plugin_classes
    
    def load_plugins_from_file(self, file_path: Path) -> List[Type[PluginBase]]:
        """从文件加载插件类"""
        # 生成模块名
        if file_path.parent.name == "core":
            module_name = f"plugins.core.{file_path.stem}"
        else:
            module_name = f"plugins.custom.{file_path.stem}"
        
        # 检查模块是否已加载
        if module_name in self.loaded_modules:
            self.logger.debug(f"Module {module_name} already loaded")
            return []
        
        try:
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 标记模块为已加载
            self.loaded_modules.add(module_name)
            
            # 查找插件类
            plugin_classes = self._find_plugin_classes(module)
            
            self.logger.debug(f"Loaded {len(plugin_classes)} plugins from {file_path}")
            return plugin_classes
            
        except Exception as e:
            self.logger.error(f"Error loading plugins from {file_path}: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _find_plugin_classes(self, module) -> List[Type[PluginBase]]:
        """查找模块中的插件类"""
        import inspect
        plugin_classes = []
        
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and 
                issubclass(obj, PluginBase) and 
                obj != PluginBase):
                plugin_classes.append(obj)
        
        return plugin_classes
    
    def unload_module(self, module_name: str):
        """卸载模块"""
        if module_name in self.loaded_modules:
            self.loaded_modules.remove(module_name)
            
            # 从sys.modules中移除模块
            if module_name in importlib.sys.modules:
                del importlib.sys.modules[module_name]
            
            self.logger.debug(f"Unloaded module: {module_name}")
    
    def clear_loaded_modules(self):
        """清空已加载的模块"""
        self.loaded_modules.clear()
        self.logger.debug("Cleared loaded modules")
