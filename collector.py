"""
ماژول جمع‌آوری داده

این ماژول کلاس پایه برای جمع‌آوری داده را تعریف می‌کند.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Type, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from twitter_analysis.api.interfaces import SearchParameters, TweetData, TwitterAPIClient
from twitter_analysis.config.settings import settings
from twitter_analysis.core.exceptions import CollectorError
from twitter_analysis.data.database import get_db_session
from twitter_analysis.data.models import Collection, CollectionStatus
from twitter_analysis.data.repositories import (CollectionRepository, KeywordRepository,
                                               TweetRepository, UserRepository)

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='BaseCollector')


class BaseCollector(ABC):
    """کلاس پایه برای جمع‌آوری داده"""
    
    def __init__(
        self, 
        twitter_client: TwitterAPIClient,
        collection_id: Optional[str] = None
    ):
        self.twitter_client = twitter_client
        self.collection_id = collection_id
        self.batch_size = settings.collector.batch_size
    
    @abstractmethod
    async def collect(self) -> List[TweetData]:
        """جمع‌آوری داده‌های مورد نظر"""
        pass
    
    @abstractmethod
    async def save(self, tweets: List[TweetData]) -> int:
        """ذخیره داده‌های جمع‌آوری شده"""
        pass
    
    async def run(self) -> Tuple[int, int]:
        """اجرای فرآیند جمع‌آوری و ذخیره‌سازی"""
        try:
            # جمع‌آوری داده‌ها
            logger.info(f"Starting data collection with {self.__class__.__name__}")
            tweets = await self.collect()
            logger.info(f"Collected {len(tweets)} tweets")
            
            # ذخیره داده‌ها
            if tweets:
                saved_count = await self.save(tweets)
                logger.info(f"Saved {saved_count} tweets to database")
                return len(tweets), saved_count
            
            return 0, 0
            
        except Exception as e:
            logger.error(f"Error in collection process: {str(e)}", exc_info=True)
            raise CollectorError(f"Collection failed: {str(e)}")
    
    async def update_collection_status(
        self, 
        collection_id: str, 
        collected_count: int, 
        saved_count: int
    ) -> None:
        """به‌روزرسانی وضعیت جمع‌آوری"""
        if not collection_id:
            return
        
        try:
            async with get_db_session() as session:
                repo = CollectionRepository(session)
                collection = await repo.get_by_id(collection_id)
                
                if collection:
                    # محاسبه زمان اجرای بعدی
                    next_run_at = datetime.utcnow() + timedelta(seconds=collection.interval_seconds)
                    
                    # ذخیره آخرین وضعیت
                    current_stats = collection.parameters.get("stats", {}) if collection.parameters else {}
                    last_run = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "collected": collected_count,
                        "saved": saved_count
                    }
                    
                    # به‌روزرسانی آمار
                    total_collected = current_stats.get("total_collected", 0) + collected_count
                    total_saved = current_stats.get("total_saved", 0) + saved_count
                    
                    new_stats = {
                        "total_collected": total_collected,
                        "total_saved": total_saved,
                        "last_run": last_run,
                        "run_count": current_stats.get("run_count", 0) + 1
                    }
                    
                    # به‌روزرسانی پارامترها
                    params = collection.parameters or {}
                    params["stats"] = new_stats
                    
                    # به‌روزرسانی جمع‌آوری
                    await repo.update(
                        collection_id,
                        last_run_at=datetime.utcnow(),
                        next_run_at=next_run_at,
                        parameters=params
                    )
                    
                    logger.info(f"Updated collection {collection_id} status")
                else:
                    logger.warning(f"Collection {collection_id} not found for status update")
                    
        except Exception as e:
            logger.error(f"Error updating collection status: {str(e)}", exc_info=True)
    
    @classmethod
    async def process_collection(
        cls: Type[T], 
        collection: Collection, 
        twitter_client: TwitterAPIClient
    ) -> Tuple[int, int]:
        """پردازش یک جمع‌آوری"""
        # ایجاد نمونه از جمع‌کننده
        collector = cls(twitter_client, str(collection.id))
        
        # اجرای جمع‌آوری
        collected, saved = await collector.run()
        
        # به‌روزرسانی وضعیت جمع‌آوری
        await collector.update_collection_status(str(collection.id), collected, saved)
        
        return collected, saved


class TweetSaver:
    """کلاس کمکی برای ذخیره توییت‌ها در دیتابیس"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.tweet_repo = TweetRepository(session)
        self.keyword_repo = KeywordRepository(session)
    
    async def save_tweet(
        self, 
        tweet_data: TweetData, 
        keywords: Optional[Set[str]] = None
    ) -> Tuple[bool, str]:
        """ذخیره یک توییت و کاربر مرتبط با آن"""
        try:
            # ۱. ابتدا کاربر را ذخیره می‌کنیم
            user = await self.user_repo.create_or_update(
                twitter_id=tweet_data.author_id,
                username=tweet_data.author_username,
                display_name=tweet_data.author_name,
                twitter_created_at=None,  # نیاز به داده کامل کاربر داریم
                raw_data={"username": tweet_data.author_username, "name": tweet_data.author_name}
            )
            
            # ۲. سپس توییت را ذخیره می‌کنیم
            tweet = await self.tweet_repo.create_or_update(
                twitter_id=tweet_data.tweet_id,
                user_id=user.id,
                text=tweet_data.text,
                created_at=tweet_data.created_at,
                retweet_count=tweet_data.retweet_count,
                like_count=tweet_data.like_count,
                reply_count=tweet_data.reply_count,
                quote_count=tweet_data.quote_count,
                view_count=tweet_data.view_count,
                language=tweet_data.language,
                source=tweet_data.source,
                raw_data=tweet_data.raw_data
            )
            
            # ۳. اگر کلیدواژه‌ها مشخص شده باشند، آن‌ها را به توییت مرتبط می‌کنیم
            if keywords:
                for keyword_text in keywords:
                    keyword = await self.keyword_repo.get_or_create(text=keyword_text)
                    await self.keyword_repo.associate_with_tweet(keyword.id, tweet.id)
            
            return True, str(tweet.id)
            
        except Exception as e:
            logger.error(f"Error saving tweet {tweet_data.tweet_id}: {str(e)}", exc_info=True)
            return False, ""