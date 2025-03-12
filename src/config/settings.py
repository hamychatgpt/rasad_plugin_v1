"""
ماژول تنظیمات برنامه

این ماژول تنظیمات برنامه را از فایل‌های env و YAML می‌خواند و در قالب
کلاس‌های پایدانتیک در دسترس قرار می‌دهد.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Union, Any 

import yaml
from dotenv import load_dotenv, find_dotenv
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings

# پیدا کردن مسیر فایل .env
env_path = find_dotenv()
print(f"Loading environment from: {env_path or 'Not found'}")

# چاپ مقدار API key (فقط چند کاراکتر اول برای امنیت)
api_key = os.environ.get("TWITTER_API_KEY", "")
if api_key:
    print(f"TWITTER_API_KEY found in environment: {api_key[:4]}...")
else:
    print("TWITTER_API_KEY not found in environment")

get_settings.cache_clear() if 'get_settings' in globals() else None
load_yaml_config.cache_clear() if 'load_yaml_config' in globals() else None

# بارگذاری مجدد با override=True
load_dotenv(override=True)

# مسیر پایه پروژه
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class DatabaseSettings(BaseModel):
    """تنظیمات دیتابیس"""
    url: str = Field(default="sqlite:///./rasad.db", alias="DATABASE_URL")
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800

    class Config:
        env_prefix = ""


class TwitterAPISettings(BaseModel):
    """تنظیمات Twitter API"""
    api_key: str = Field(default="", alias="TWITTER_API_KEY")
    base_url: str = "https://api.twitterapi.io"
    # کد بقیه

    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """اعتبارسنجی کلید API توییتر"""
        if not v or v == "missing_api_key":
            logger.warning("Twitter API key is missing or invalid")
        return v

class AnthropicAPISettings(BaseModel):
    """تنظیمات Anthropic API"""
    api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    default_model: str = "claude-3-7-sonnet-20250219"
    # کد بقیه

    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """اعتبارسنجی کلید API آنتروپیک"""
        if not v or v == "missing_api_key":
            logger.warning("Anthropic API key is missing or invalid")
        return v
    
class CollectorSettings(BaseModel):
    """تنظیمات جمع‌کننده داده"""
    default_interval: int = 300  # ثانیه
    batch_size: int = 100
    min_interval: int = 60  # ثانیه
    max_interval: int = 3600  # ثانیه
    default_query_type: str = "Latest"


class WebSettings(BaseModel):
    """تنظیمات وب"""
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    templates_dir: str = "templates"
    static_dir: str = "static"
    default_lang: str = "fa"
    default_page_size: int = 20
    max_page_size: int = 100


class Settings(BaseSettings):
    """تنظیمات اصلی برنامه"""
    app_env: str = Field(default="production", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")
    secret_key: str = Field(default="default_secret_key", alias="SECRET_KEY")
    
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    twitter_api: TwitterAPISettings = Field(default_factory=TwitterAPISettings)
    anthropic_api: AnthropicAPISettings = Field(default_factory=AnthropicAPISettings)
    collector: CollectorSettings = Field(default_factory=CollectorSettings)
    web: WebSettings = Field(default_factory=WebSettings)

    # تغییر validator به field_validator
    @field_validator("database", mode="before")  # mode='before' معادل pre=True
    @classmethod  # اضافه کردن @classmethod
    def create_database_settings(cls, v):  # حذف values
        """ساخت تنظیمات دیتابیس با استفاده از مقادیر محیطی"""
        if isinstance(v, Dict):
            return v
        return DatabaseSettings()
    
    @field_validator("twitter_api", mode="before")
    @classmethod
    def create_twitter_api_settings(cls, v):
        """ساخت تنظیمات Twitter API با استفاده از مقادیر محیطی"""
        if isinstance(v, Dict):
            return v
        return TwitterAPISettings()
    
    @field_validator("anthropic_api", mode="before")
    @classmethod
    def create_anthropic_api_settings(cls, v):
        """ساخت تنظیمات Anthropic API با استفاده از مقادیر محیطی"""
        if isinstance(v, Dict):
            return v
        return AnthropicAPISettings()

    # تغییر Config به model_config
    model_config = {
        "extra": "ignore",  # اجازه دادن فیلدهای اضافی
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

@lru_cache()
def load_yaml_config() -> Dict[str, Any]:
    """بارگذاری تنظیمات از فایل YAML"""
    config_path = BASE_DIR / "src" / "config" / "config.yaml"
    if not config_path.exists():
        config_path = BASE_DIR / "config" / "config.yaml"
        if not config_path.exists():
            return {}
    
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache()
def get_settings() -> Settings:
    """دریافت تنظیمات برنامه"""
    # ترکیب تنظیمات YAML و محیطی
    yaml_config = load_yaml_config()
    
    # استفاده از تنظیمات YAML برای مقادیر پیش‌فرض
    if yaml_config:
        twitter_api_config = yaml_config.get("twitter_api", {})
        if twitter_api_config:
            TwitterAPISettings.default_qps = twitter_api_config.get("rate_limits", {}).get("default_qps", 200)
            TwitterAPISettings.default_rpm = twitter_api_config.get("rate_limits", {}).get("default_rpm", 12000)
            TwitterAPISettings.base_url = twitter_api_config.get("base_url", "https://api.twitterapi.io")
            
            retry_config = twitter_api_config.get("retry", {})
            if retry_config:
                TwitterAPISettings.max_attempts = retry_config.get("max_attempts", 5)
                TwitterAPISettings.initial_delay = retry_config.get("initial_delay", 1.0)
                TwitterAPISettings.exponential_factor = retry_config.get("exponential_factor", 2.0)
                TwitterAPISettings.jitter = retry_config.get("jitter", 0.1)
        
        anthropic_api_config = yaml_config.get("anthropic_api", {})
        if anthropic_api_config:
            models_config = anthropic_api_config.get("models", {})
            if models_config:
                AnthropicAPISettings.default_model = models_config.get("default", "claude-3-7-sonnet-20250219")
                AnthropicAPISettings.fallback_model = models_config.get("fallback", "claude-3-5-sonnet-20241022")
            
            options_config = anthropic_api_config.get("options", {})
            if options_config:
                AnthropicAPISettings.max_tokens = options_config.get("max_tokens", 1024)
                AnthropicAPISettings.temperature = options_config.get("temperature", 0.7)
        
        collector_config = yaml_config.get("collector", {})
        if collector_config:
            CollectorSettings.default_interval = collector_config.get("default_interval", 300)
            CollectorSettings.batch_size = collector_config.get("batch_size", 100)
            
            keyword_search_config = collector_config.get("keyword_search", {})
            if keyword_search_config:
                CollectorSettings.min_interval = keyword_search_config.get("min_interval", 60)
                CollectorSettings.max_interval = keyword_search_config.get("max_interval", 3600)
                CollectorSettings.default_query_type = keyword_search_config.get("default_query_type", "Latest")
        
        web_config = yaml_config.get("web", {})
        if web_config:
            WebSettings.templates_dir = web_config.get("templates_dir", "templates")
            WebSettings.static_dir = web_config.get("static_dir", "static")
            WebSettings.default_lang = web_config.get("default_lang", "fa")
            
            pagination_config = web_config.get("pagination", {})
            if pagination_config:
                WebSettings.default_page_size = pagination_config.get("default_page_size", 20)
                WebSettings.max_page_size = pagination_config.get("max_page_size", 100)
    
    return Settings()


settings = get_settings()