"""
واسط‌های انتزاعی برای API‌های خارجی

این ماژول واسط‌های انتزاعی برای تعامل با API‌های خارجی را تعریف می‌کند.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel


class TweetData(BaseModel):
    """مدل داده توییت"""
    tweet_id: str
    text: str
    created_at: datetime
    author_id: str
    author_username: str
    author_name: str
    retweet_count: int = 0
    reply_count: int = 0
    like_count: int = 0
    quote_count: int = 0
    view_count: Optional[int] = None
    language: Optional[str] = None
    source: Optional[str] = None
    raw_data: Dict[str, Any]


class UserData(BaseModel):
    """مدل داده کاربر"""
    user_id: str
    username: str
    display_name: str
    description: Optional[str] = None
    followers_count: int = 0
    following_count: int = 0
    created_at: datetime
    verified: bool = False
    profile_image_url: Optional[str] = None
    raw_data: Dict[str, Any]


class SearchParameters(BaseModel):
    """پارامترهای جستجوی توییت"""
    query: str
    query_type: str = "Latest"
    cursor: Optional[str] = None


class TwitterAPIClient(ABC):
    """واسط انتزاعی برای کلاینت Twitter API"""
    
    @abstractmethod
    async def search_tweets(self, params: SearchParameters) -> List[TweetData]:
        """جستجوی توییت‌ها بر اساس پارامترهای داده شده"""
        pass
    
    @abstractmethod
    async def get_user_info(self, username: str) -> UserData:
        """دریافت اطلاعات کاربر با نام کاربری"""
        pass
    
    @abstractmethod
    async def get_user_tweets(
        self, 
        user_id: str, 
        include_replies: bool = False, 
        cursor: Optional[str] = None
    ) -> List[TweetData]:
        """دریافت توییت‌های اخیر یک کاربر"""
        pass
    
    @abstractmethod
    async def get_tweets_by_ids(self, tweet_ids: List[str]) -> List[TweetData]:
        """دریافت توییت‌ها با شناسه‌های داده شده"""
        pass


class SentimentAnalysisResult(BaseModel):
    """نتیجه تحلیل احساسات"""
    sentiment: str  # 'positive', 'neutral', 'negative'
    confidence: float  # 0.0 to 1.0
    text_snippet: str
    justification: Optional[str] = None


class TopicExtractionResult(BaseModel):
    """نتیجه استخراج موضوع"""
    topics: List[str]
    confidence: Dict[str, float]
    summary: Optional[str] = None


class TextAnalysisRequest(BaseModel):
    """درخواست تحلیل متن"""
    text: str
    analysis_type: str  # 'sentiment', 'topic', 'entity', etc.
    options: Optional[Dict[str, Any]] = None


class TextAnalysisResponse(BaseModel):
    """پاسخ تحلیل متن"""
    request_id: str
    analysis_type: str
    result: Union[SentimentAnalysisResult, TopicExtractionResult, Dict[str, Any]]
    raw_response: Optional[Dict[str, Any]] = None
    processing_time: float  # seconds


class TextAnalysisClient(ABC):
    """واسط انتزاعی برای کلاینت تحلیل متن"""
    
    @abstractmethod
    async def analyze_text(self, request: TextAnalysisRequest) -> TextAnalysisResponse:
        """تحلیل متن با استفاده از API"""
        pass
    
    @abstractmethod
    async def sentiment_analysis(self, text: str) -> SentimentAnalysisResult:
        """تحلیل احساسات متن"""
        pass
    
    @abstractmethod
    async def topic_extraction(self, text: str) -> TopicExtractionResult:
        """استخراج موضوعات از متن"""
        pass