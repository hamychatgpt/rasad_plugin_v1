"""
استثناهای سفارشی برنامه

این ماژول استثناهای سفارشی برنامه را تعریف می‌کند.
"""

from typing import Any, Dict, Optional


class TwitterAnalysisError(Exception):
    """کلاس پایه برای تمام استثناهای برنامه"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ConfigurationError(TwitterAnalysisError):
    """خطای پیکربندی برنامه"""
    pass


class APIError(TwitterAnalysisError):
    """خطای مربوط به تعامل با API‌های خارجی"""
    
    def __init__(
        self, 
        message: str, 
        status_code: Optional[int] = None, 
        response_body: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message, details)


class TwitterAPIError(APIError):
    """خطای مربوط به Twitter API"""
    pass


class AnthropicAPIError(APIError):
    """خطای مربوط به Anthropic API"""
    pass


class RateLimitError(APIError):
    """خطای محدودیت نرخ API"""
    
    def __init__(
        self, 
        message: str, 
        retry_after: Optional[int] = None,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code, response_body, details)


class DatabaseError(TwitterAnalysisError):
    """خطای مربوط به دیتابیس"""
    pass


class CollectorError(TwitterAnalysisError):
    """خطای مربوط به جمع‌آوری داده"""
    pass


class ProcessorError(TwitterAnalysisError):
    """خطای مربوط به پردازش داده"""
    pass


class ValidationError(TwitterAnalysisError):
    """خطای اعتبارسنجی داده"""
    pass