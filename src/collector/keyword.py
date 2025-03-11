"""
جمع‌کننده توییت بر اساس کلیدواژه

این ماژول جمع‌کننده ای برای یافتن توییت‌ها بر اساس کلیدواژه ارائه می‌دهد.
"""

import logging
from typing import List, Optional, Set, Tuple

from src.api.interfaces import SearchParameters, TweetData, TwitterAPIClient
from src.collector.collector import BaseCollector, TweetSaver
from src.config.settings import settings
from src.core.exceptions import CollectorError
from src.data.database import get_db_session
from src.data.models import Collection, CollectionType
from src.data.repositories import CollectionRepository, KeywordRepository

logger = logging.getLogger(__name__)


class KeywordCollector(BaseCollector):
    """جمع‌کننده توییت بر اساس کلیدواژه"""
    
    def __init__(
        self, 
        twitter_client: TwitterAPIClient,
        collection_id: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        query_type: str = "Latest",
        cursor: Optional[str] = None
    ):
        super().__init__(twitter_client, collection_id)
        self.keywords = keywords or []
        self.query_type = query_type
        self.cursor = cursor
        self.collected_keywords: Set[str] = set()
    
    async def load_collection_keywords(self) -> None:
        """بارگذاری کلیدواژه‌ها از جمع‌آوری"""
        if not self.collection_id:
            return
        
        async with get_db_session() as session:
            repo = CollectionRepository(session)
            collection = await repo.get_by_id(self.collection_id)
            
            if not collection:
                raise CollectorError(f"Collection {self.collection_id} not found")
            
            if collection.collection_type != CollectionType.KEYWORD:
                raise CollectorError(f"Collection {self.collection_id} is not a keyword collection")
            
            # بارگذاری پارامترهای جمع‌آوری
            params = collection.parameters or {}
            self.query_type = params.get("query_type", settings.collector.default_query_type)
            self.cursor = params.get("cursor")
            
            # بارگذاری کلیدواژه‌های جمع‌آوری
            keywords = await repo.get_keywords(collection.id)
            self.keywords = [keyword.text for keyword in keywords]
            
            if not self.keywords:
                logger.warning(f"No keywords found for collection {self.collection_id}")
    
    async def collect(self) -> List[TweetData]:
        """جمع‌آوری توییت‌ها بر اساس کلیدواژه‌ها"""
        # اگر کلیدواژه‌ای تنظیم نشده و شناسه جمع‌آوری داریم، کلیدواژه‌ها را بارگذاری می‌کنیم
        if not self.keywords and self.collection_id:
            await self.load_collection_keywords()
        
        if not self.keywords:
            logger.warning("No keywords specified for collection")
            return []
        
        collected_tweets: List[TweetData] = []
        self.collected_keywords = set()
        
        # برای هر کلیدواژه، توییت‌ها را جمع‌آوری می‌کنیم
        for keyword in self.keywords:
            try:
                logger.info(f"Collecting tweets for keyword: {keyword}")
                
                # ساخت پارامترهای جستجو
                search_params = SearchParameters(
                    query=keyword,
                    query_type=self.query_type,
                    cursor=self.cursor
                )
                
                # جستجوی توییت‌ها
                tweets = await self.twitter_client.search_tweets(search_params)
                logger.info(f"Found {len(tweets)} tweets for keyword: {keyword}")
                
                if tweets:
                    # ذخیره کلیدواژه مربوط به هر توییت
                    for tweet in tweets:
                        tweet.raw_data["collected_keyword"] = keyword
                    
                    collected_tweets.extend(tweets)
                    self.collected_keywords.add(keyword)
            
            except Exception as e:
                logger.error(f"Error collecting tweets for keyword {keyword}: {str(e)}", exc_info=True)
        
        return collected_tweets
    
    async def save(self, tweets: List[TweetData]) -> int:
        """ذخیره توییت‌های جمع‌آوری شده"""
        if not tweets:
            return 0
        
        saved_count = 0
        
        async with get_db_session() as session:
            tweet_saver = TweetSaver(session)
            
            for tweet in tweets:
                # استخراج کلیدواژه مربوط به این توییت
                keyword = tweet.raw_data.get("collected_keyword")
                keywords = {keyword} if keyword else self.collected_keywords
                
                # ذخیره توییت
                success, _ = await tweet_saver.save_tweet(tweet, keywords)
                if success:
                    saved_count += 1
            
            # ذخیره مقدار cursor جدید برای جمع‌آوری بعدی (در صورتی که شناسه جمع‌آوری داشته باشیم)
            if self.collection_id and tweets:
                # فرض می‌کنیم آخرین توییت حاوی اطلاعات cursor است
                cursor = tweets[-1].raw_data.get("cursor")
                
                if cursor:
                    collection_repo = CollectionRepository(session)
                    collection = await collection_repo.get_by_id(self.collection_id)
                    
                    if collection:
                        params = collection.parameters or {}
                        params["cursor"] = cursor
                        await collection_repo.update(collection.id, parameters=params)
        
        return saved_count


async def collect_by_keywords(
    twitter_client: TwitterAPIClient,
    keywords: List[str],
    query_type: str = "Latest"
) -> Tuple[int, int]:
    """تابع کمکی برای جمع‌آوری توییت‌ها بر اساس کلیدواژه‌ها"""
    collector = KeywordCollector(
        twitter_client=twitter_client,
        keywords=keywords,
        query_type=query_type
    )
    return await collector.run()