"""
خط لوله پردازش داده

این ماژول خط لوله پردازش داده را تعریف می‌کند.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from src.data.database import get_db_session
from src.data.models import Tweet
from src.data.repositories import TweetRepository
from src.processor.filters import FilterPipeline, create_basic_filter_pipeline

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='ProcessorStep')


class ProcessorStep(ABC):
    """مرحله پردازش"""
    
    @abstractmethod
    async def process(self, tweet: Tweet, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """پردازش یک توییت
        
        Returns:
            Tuple[bool, Dict[str, Any]]: نتیجه پردازش (ادامه/توقف، اطلاعات بافت به‌روزشده)
        """
        pass


class FilterStep(ProcessorStep):
    """مرحله فیلترینگ"""
    
    def __init__(self, filter_pipeline: Optional[FilterPipeline] = None):
        self.filter_pipeline = filter_pipeline or create_basic_filter_pipeline()
    
    async def process(self, tweet: Tweet, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """فیلتر کردن توییت"""
        # اعمال فیلترها
        if self.filter_pipeline.apply_all(tweet):
            # توییت فیلترها را گذراند، ادامه می‌دهیم
            return True, context
        else:
            # توییت فیلترها را نگذراند، از پردازش خارج می‌شویم
            return False, context


class TweetProcessingPipeline:
    """خط لوله پردازش توییت"""
    
    def __init__(self, steps: Optional[List[ProcessorStep]] = None):
        self.steps = steps or []
        self.setup_default_steps()
    
    def setup_default_steps(self) -> None:
        """تنظیم مراحل پیش‌فرض پردازش"""
        if not self.steps:
            # در ابتدا فقط از فیلترینگ استفاده می‌کنیم
            self.steps.append(FilterStep())
    
    def add_step(self, step: ProcessorStep) -> None:
        """افزودن یک مرحله به خط لوله"""
        self.steps.append(step)
    
    async def process_tweet(self, tweet: Tweet) -> Tuple[bool, Dict[str, Any]]:
        """پردازش یک توییت با تمام مراحل"""
        context: Dict[str, Any] = {}
        
        for step in self.steps:
            try:
                continue_pipeline, context = await step.process(tweet, context)
                
                if not continue_pipeline:
                    logger.debug(f"Tweet {tweet.id} stopped at step {step.__class__.__name__}")
                    return False, context
                    
            except Exception as e:
                logger.error(f"Error processing tweet {tweet.id} at step {step.__class__.__name__}: {str(e)}")
                return False, context
        
        # همه مراحل با موفقیت انجام شد
        return True, context
    
    async def process_tweets(self, tweets: List[Tweet]) -> List[Tuple[Tweet, bool, Dict[str, Any]]]:
        """پردازش لیستی از توییت‌ها"""
        results = []
        
        for tweet in tweets:
            success, context = await self.process_tweet(tweet)
            results.append((tweet, success, context))
        
        return results
    
    @classmethod
    async def process_all_unprocessed(cls: Type['TweetProcessingPipeline'], limit: int = 100) -> int:
        """پردازش تمام توییت‌های پردازش نشده"""
        pipeline = cls()
        processed_count = 0
        
        async with get_db_session() as session:
            # در فاز اول، معیار "پردازش شده" را نداریم، بنابراین همه توییت‌ها را می‌گیریم
            # در فازهای بعدی می‌توان با اضافه کردن فیلد processed به توییت‌ها، فقط توییت‌های پردازش نشده را پردازش کرد
            tweet_repo = TweetRepository(session)
            tweets = await tweet_repo.list(limit=limit)
            
            if not tweets:
                logger.info("No tweets to process")
                return 0
            
            logger.info(f"Processing {len(tweets)} tweets")
            
            # پردازش توییت‌ها
            results = await pipeline.process_tweets(tweets)
            
            # شمارش توییت‌های پردازش شده با موفقیت
            for tweet, success, context in results:
                if success:
                    processed_count += 1
                    
                    # در فازهای بعدی، می‌توان وضعیت پردازش را ذخیره کرد
                    # await tweet_repo.update(tweet.id, processed=True)
            
            logger.info(f"Successfully processed {processed_count} tweets")
            
            return processed_count