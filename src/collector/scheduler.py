"""
زمان‌بندی جمع‌آوری داده

این ماژول مسئول زمان‌بندی و اجرای جمع‌آوری‌های داده است.
"""

import asyncio
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Type

from src.api.interfaces import TwitterAPIClient
from src.api.twitter import create_twitter_client
from src.collector.collector import BaseCollector
from src.collector.keyword import KeywordCollector
from src.core.exceptions import CollectorError
from src.core.plugin import Plugin
from src.data.database import get_db_session
from src.data.models import Collection, CollectionStatus, CollectionType
from src.data.repositories import CollectionRepository

logger = logging.getLogger(__name__)


class CollectorScheduler:
    """زمان‌بند جمع‌آوری داده"""
    
    def __init__(self, twitter_client: TwitterAPIClient):
        self.twitter_client = twitter_client
        self.running = False
        self.collector_types: Dict[CollectionType, Type[BaseCollector]] = {
            CollectionType.KEYWORD: KeywordCollector,
            # سایر انواع جمع‌کننده در فازهای بعدی اضافه می‌شوند
        }
    
    async def get_due_collections(self) -> List[Collection]:
        """دریافت جمع‌آوری‌هایی که زمان اجرای آن‌ها فرا رسیده است"""
        async with get_db_session() as session:
            repo = CollectionRepository(session)
            return await repo.get_due_collections()
    
    async def process_collection(self, collection: Collection) -> bool:
        """پردازش یک جمع‌آوری"""
        try:
            # دریافت نوع جمع‌کننده مناسب
            collector_class = self.collector_types.get(collection.collection_type)
            
            if not collector_class:
                logger.error(f"No collector found for collection type {collection.collection_type}")
                return False
            
            # پردازش جمع‌آوری
            collected, saved = await collector_class.process_collection(
                collection=collection,
                twitter_client=self.twitter_client
            )
            
            logger.info(f"Processed collection {collection.name}: collected={collected}, saved={saved}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing collection {collection.name}: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    async def run_once(self) -> int:
        """اجرای یک دور زمان‌بندی"""
        try:
            # دریافت جمع‌آوری‌های آماده برای اجرا
            collections = await self.get_due_collections()
            
            if not collections:
                logger.debug("No collections due for collection")
                return 0
            
            logger.info(f"Found {len(collections)} collections due for collection")
            
            # پردازش هر جمع‌آوری
            processed_count = 0
            for collection in collections:
                try:
                    success = await self.process_collection(collection)
                    if success:
                        processed_count += 1
                except Exception as e:
                    logger.error(f"Error processing collection {collection.name}: {str(e)}")
            
            return processed_count
            
        except Exception as e:
            logger.error(f"Error in scheduler run: {str(e)}")
            return 0
    
    async def run(self, interval_seconds: int = 60) -> None:
        """اجرای زمان‌بند در حلقه تکرار"""
        self.running = True
        
        while self.running:
            try:
                processed = await self.run_once()
                logger.info(f"Scheduler processed {processed} collections")
                
            except Exception as e:
                logger.error(f"Scheduler error: {str(e)}")
            
            # انتظار برای اجرای بعدی
            await asyncio.sleep(interval_seconds)
    
    def stop(self) -> None:
        """توقف زمان‌بند"""
        self.running = False


class CollectorPlugin(Plugin):
    """پلاگین جمع‌کننده داده"""
    
    @property
    def name(self) -> str:
        return "collector"
    
    @property
    def version(self) -> str:
        return "0.1.0"
    
    @property
    def description(self) -> str:
        return "جمع‌آوری داده از توییتر بر اساس کلیدواژه و سایر پارامترها"
    
    def initialize(self) -> None:
        """راه‌اندازی پلاگین"""
        # ایجاد کلاینت توییتر
        twitter_client = create_twitter_client()
        
        # ایجاد زمان‌بند جمع‌آوری داده
        self.scheduler = CollectorScheduler(twitter_client)
        
        # راه‌اندازی زمان‌بند در یک task جداگانه
        self.task = asyncio.create_task(self.scheduler.run())
        
        logger.info("CollectorPlugin initialized")
    
    def shutdown(self) -> None:
        """خاموش کردن پلاگین"""
        if hasattr(self, "scheduler"):
            self.scheduler.stop()
        
        if hasattr(self, "task"):
            self.task.cancel()
        
        logger.info("CollectorPlugin shutdown")