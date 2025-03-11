"""
سیستم پلاگین‌ها

این ماژول یک سیستم پلاگین ساده ارائه می‌دهد که به ما اجازه می‌دهد 
قابلیت‌های جدید را به صورت ماژولار به برنامه اضافه کنیم.
"""

import importlib
import inspect
import pkgutil
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, TypeVar

from twitter_analysis.core.di import container

T = TypeVar('T', bound='Plugin')


class Plugin(ABC):
    """کلاس پایه برای تمام پلاگین‌ها"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """نام پلاگین"""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """نسخه پلاگین"""
        pass
    
    @property
    def description(self) -> str:
        """توضیحات پلاگین"""
        return ""
    
    @abstractmethod
    def initialize(self) -> None:
        """راه‌اندازی پلاگین"""
        pass
    
    def shutdown(self) -> None:
        """خاموش کردن پلاگین"""
        pass


class PluginManager:
    """مدیریت پلاگین‌های برنامه"""
    
    def __init__(self) -> None:
        self._plugins: Dict[str, Plugin] = {}
    
    def register_plugin(self, plugin: Plugin) -> None:
        """ثبت یک پلاگین"""
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin with name '{plugin.name}' is already registered")
        
        self._plugins[plugin.name] = plugin
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """دریافت پلاگین با نام مشخص"""
        return self._plugins.get(name)
    
    def get_all_plugins(self) -> List[Plugin]:
        """دریافت تمام پلاگین‌های ثبت شده"""
        return list(self._plugins.values())
    
    def initialize_all(self) -> None:
        """راه‌اندازی تمام پلاگین‌ها"""
        for plugin in self._plugins.values():
            plugin.initialize()
    
    def shutdown_all(self) -> None:
        """خاموش کردن تمام پلاگین‌ها"""
        for plugin in self._plugins.values():
            plugin.shutdown()
    
    def discover_plugins(self, package_name: str) -> None:
        """کشف خودکار پلاگین‌ها از یک پکیج"""
        package = importlib.import_module(package_name)
        
        for _, name, is_pkg in pkgutil.iter_modules(package.__path__, package.__name__ + '.'):
            if not is_pkg:
                module = importlib.import_module(name)
                for _, obj in inspect.getmembers(module):
                    # پیدا کردن کلاس‌های پلاگین
                    if (inspect.isclass(obj) and 
                        issubclass(obj, Plugin) and 
                        obj != Plugin and 
                        not inspect.isabstract(obj)):
                        try:
                            instance = obj()
                            self.register_plugin(instance)
                        except Exception as e:
                            print(f"Error instantiating plugin {obj.__name__}: {e}")


# ایجاد نمونه سراسری از مدیریت پلاگین‌ها
plugin_manager = PluginManager()

# ثبت مدیریت پلاگین‌ها در مخزن وابستگی‌ها
container.register_instance(PluginManager, plugin_manager)