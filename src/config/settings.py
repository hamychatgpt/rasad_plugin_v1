# فایل جایگزین settings.py ساده‌شده
import os
from pathlib import Path

# تنظیمات پایه
DEBUG = True
SECRET_KEY = "dpl2QsHvI1CROJXzpPBiQPuX_d9ZphKoMDvPWlnzMag"

# تنظیمات دیتابیس
DATABASE_URL = "sqlite:///./rasad.db"

# تنظیمات API
TWITTER_API_KEY = "cf5800d7a52a4df89b5df7ffe1c7303d"
ANTHROPIC_API_KEY = "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"

# تنظیمات وب
HOST = "0.0.0.0"
PORT = 8000

# ساختارهای داده برای استفاده در برنامه
class Settings:
    debug = DEBUG
    secret_key = SECRET_KEY
    
    class database:
        url = DATABASE_URL
        pool_size = 5
        max_overflow = 10
        pool_timeout = 30
        pool_recycle = 1800
    
    class twitter_api:
        api_key = TWITTER_API_KEY
        base_url = "https://api.twitterapi.io"
        default_qps = 200
        default_rpm = 12000
        max_attempts = 5
        initial_delay = 1.0
        exponential_factor = 2.0
        jitter = 0.1
    
    class anthropic_api:
        api_key = ANTHROPIC_API_KEY
        default_model = "claude-3-7-sonnet-20250219"
        fallback_model = "claude-3-5-sonnet-20241022"
        max_tokens = 1024
        temperature = 0.7
    
    class collector:
        default_interval = 300
        batch_size = 100
        min_interval = 60
        max_interval = 3600
        default_query_type = "Latest"
    
    class web:
        host = HOST
        port = PORT
        templates_dir = "templates"
        static_dir = "static"
        default_lang = "fa"
        default_page_size = 20
        max_page_size = 100

# ایجاد نمونه تنظیمات برای استفاده در سراسر برنامه
settings = Settings()