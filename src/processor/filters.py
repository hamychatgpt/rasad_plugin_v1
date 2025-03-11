"""
فیلترهای پردازش داده

این ماژول فیلترهای مختلف برای پردازش توییت‌ها را تعریف می‌کند.
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Union

from src.data.models import Tweet

logger = logging.getLogger(__name__)


class BaseFilter(ABC):
    """کلاس پایه برای فیلترها"""
    
    @abstractmethod
    def apply(self, tweet: Tweet) -> bool:
        """اعمال فیلتر روی توییت و برگرداندن نتیجه"""
        pass


class LanguageFilter(BaseFilter):
    """فیلتر بر اساس زبان"""
    
    def __init__(self, allowed_languages: List[str]):
        self.allowed_languages = set(allowed_languages)
    
    def apply(self, tweet: Tweet) -> bool:
        """بررسی می‌کند که آیا توییت به زبان مجاز است"""
        # اگر هیچ زبانی مشخص نشده باشد، همه زبان‌ها مجاز هستند
        if not self.allowed_languages:
            return True
        
        # اگر توییت زبان ندارد، آن را قبول می‌کنیم
        if not tweet.language:
            return True
        
        return tweet.language in self.allowed_languages


class KeywordFilter(BaseFilter):
    """فیلتر بر اساس کلید واژه‌ها"""
    
    def __init__(self, include_keywords: List[str], exclude_keywords: List[str] = None):
        self.include_patterns = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE) for kw in include_keywords]
        self.exclude_patterns = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE) for kw in (exclude_keywords or [])]
    
    def apply(self, tweet: Tweet) -> bool:
        """بررسی می‌کند که آیا توییت شامل کلیدواژه‌های مورد نظر است"""
        text = tweet.text.lower()
        
        # بررسی کلیدواژه‌های اجباری
        if self.include_patterns:
            if not any(pattern.search(text) for pattern in self.include_patterns):
                return False
        
        # بررسی کلیدواژه‌های ممنوع
        if self.exclude_patterns:
            if any(pattern.search(text) for pattern in self.exclude_patterns):
                return False
        
        return True


class EngagementFilter(BaseFilter):
    """فیلتر بر اساس میزان تعامل"""
    
    def __init__(
        self, 
        min_likes: int = 0, 
        min_retweets: int = 0, 
        min_replies: int = 0,
        min_quotes: int = 0,
        min_total: int = 0
    ):
        self.min_likes = min_likes
        self.min_retweets = min_retweets
        self.min_replies = min_replies
        self.min_quotes = min_quotes
        self.min_total = min_total
    
    def apply(self, tweet: Tweet) -> bool:
        """بررسی می‌کند که آیا توییت حداقل تعامل مورد نیاز را دارد"""
        # بررسی حداقل مقادیر جداگانه
        if tweet.like_count < self.min_likes:
            return False
        
        if tweet.retweet_count < self.min_retweets:
            return False
        
        if tweet.reply_count < self.min_replies:
            return False
        
        if tweet.quote_count < self.min_quotes:
            return False
        
        # بررسی حداقل مجموع تعاملات
        total_engagement = tweet.like_count + tweet.retweet_count + tweet.reply_count + tweet.quote_count
        if total_engagement < self.min_total:
            return False
        
        return True


class FilterPipeline:
    """خط لوله فیلترینگ توییت‌ها"""
    
    def __init__(self, filters: Optional[List[BaseFilter]] = None):
        self.filters = filters or []
    
    def add_filter(self, filter_obj: BaseFilter) -> None:
        """افزودن یک فیلتر به خط لوله"""
        self.filters.append(filter_obj)
    
    def apply_all(self, tweet: Tweet) -> bool:
        """اعمال تمام فیلترها روی یک توییت"""
        for filter_obj in self.filters:
            try:
                if not filter_obj.apply(tweet):
                    return False
            except Exception as e:
                logger.error(f"Error applying filter {filter_obj.__class__.__name__}: {str(e)}")
                # در صورت خطا در فیلتر، به صورت پیش‌فرض توییت را قبول می‌کنیم
                continue
        
        return True
    
    def filter_tweets(self, tweets: List[Tweet]) -> List[Tweet]:
        """فیلتر کردن لیستی از توییت‌ها"""
        return [tweet for tweet in tweets if self.apply_all(tweet)]


def create_basic_filter_pipeline() -> FilterPipeline:
    """ایجاد یک خط لوله فیلترینگ پایه"""
    pipeline = FilterPipeline()
    
    # فیلتر زبان - فقط فارسی و انگلیسی
    pipeline.add_filter(LanguageFilter(["fa", "en"]))
    
    # فیلتر تعامل - حداقل یک لایک یا ریتوییت
    pipeline.add_filter(EngagementFilter(min_total=1))
    
    return pipeline