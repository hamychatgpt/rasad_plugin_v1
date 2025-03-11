"""
سیستم تزریق وابستگی (Dependency Injection)

این ماژول سیستم ساده‌ای برای مدیریت وابستگی‌ها ارائه می‌دهد
که به ما کمک می‌کند تا اجزای مختلف برنامه را به صورت مجزا توسعه دهیم.
"""

from typing import Any, Callable, Dict, Optional, Type, TypeVar

T = TypeVar('T')


class Container:
    """کلاس مخزن وابستگی‌ها"""
    
    def __init__(self) -> None:
        self._providers: Dict[str, Callable[[], Any]] = {}
        self._singletons: Dict[str, Any] = {}
    
    def register(self, interface: Type[T], implementation: Type[T]) -> None:
        """ثبت یک پیاده‌سازی برای یک واسط"""
        def provider() -> T:
            return implementation()
        
        self._providers[interface.__name__] = provider
    
    def register_instance(self, interface: Type[T], instance: T) -> None:
        """ثبت یک نمونه از پیش ساخته شده برای یک واسط"""
        self._singletons[interface.__name__] = instance
    
    def register_singleton(self, interface: Type[T], implementation: Type[T]) -> None:
        """ثبت یک پیاده‌سازی به عنوان سینگلتون"""
        def provider() -> T:
            if interface.__name__ not in self._singletons:
                self._singletons[interface.__name__] = implementation()
            return self._singletons[interface.__name__]
        
        self._providers[interface.__name__] = provider
    
    def register_factory(self, interface: Type[T], factory: Callable[[], T]) -> None:
        """ثبت یک تابع سازنده برای یک واسط"""
        self._providers[interface.__name__] = factory
    
    def get(self, interface: Type[T]) -> T:
        """دریافت نمونه‌ای از یک واسط"""
        interface_name = interface.__name__
        
        # بررسی وجود نمونه سینگلتون
        if interface_name in self._singletons:
            return self._singletons[interface_name]
        
        # بررسی وجود سازنده
        if interface_name in self._providers:
            return self._providers[interface_name]()
        
        raise KeyError(f"No provider registered for {interface_name}")


# ایجاد نمونه سراسری از مخزن وابستگی‌ها
container = Container()