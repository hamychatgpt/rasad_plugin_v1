"""
فایل اجرای برنامه

این فایل برای اجرای برنامه استفاده می‌شود.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# افزودن پوشه اصلی پروژه به مسیر جستجوی پایتون
sys.path.insert(0, str(Path(__file__).parent))

from twitter_analysis.web.app import run_app

if __name__ == "__main__":
    # تنظیم لاگینگ
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("twitter_analysis.log")
        ]
    )
    
    # اجرای برنامه
    run_app()