"""
API های وب

این ماژول API های وب را تعریف می‌کند.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from twitter_analysis.api.twitter import create_twitter_client
from twitter_analysis.collector.keyword import collect_by_keywords
from twitter_analysis.config.settings import settings
from twitter_analysis.data.database import get_db_session
from twitter_analysis.data.models import Collection, CollectionStatus, CollectionType
from twitter_analysis.data.repositories import (CollectionRepository,
                                               KeywordRepository,
                                               TweetRepository, UserRepository)

logger = logging.getLogger(__name__)

router = APIRouter()


# مدل‌های API
class KeywordResponse(BaseModel):
    """مدل پاسخ کلیدواژه"""
    id: str
    text: str
    active: bool
    created_at: datetime


class TweetResponse(BaseModel):
    """مدل پاسخ توییت"""
    id: str
    tweet_id: str
    text: str
    created_at: datetime
    author_username: str
    author_name: str
    retweet_count: int
    like_count: int
    reply_count: int
    quote_count: int
    language: Optional[str] = None


class UserResponse(BaseModel):
    """مدل پاسخ کاربر"""
    id: str
    user_id: str
    username: str
    display_name: str
    followers_count: int
    following_count: int
    created_at: datetime
    verified: bool


class CollectionResponse(BaseModel):
    """مدل پاسخ جمع‌آوری"""
    id: str
    name: str
    description: Optional[str] = None
    status: str
    collection_type: str
    interval_seconds: int
    created_at: datetime
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None


class PaginatedResponse(BaseModel):
    """مدل پاسخ صفحه‌بندی شده"""
    items: List[Union[KeywordResponse, TweetResponse, UserResponse, CollectionResponse]]
    total: int
    page: int
    page_size: int
    total_pages: int


class CollectRequest(BaseModel):
    """مدل درخواست جمع‌آوری"""
    keywords: List[str] = Field(..., min_items=1)
    query_type: str = "Latest"


class CollectResponse(BaseModel):
    """مدل پاسخ جمع‌آوری"""
    success: bool
    collected: int
    saved: int


async def get_session() -> AsyncSession:
    """تابع وابستگی برای دریافت جلسه دیتابیس"""
    async with get_db_session() as session:
        yield session


@router.get("/keywords", response_model=PaginatedResponse)
async def get_keywords(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    active_only: bool = False,
    session: AsyncSession = Depends(get_session)
):
    """دریافت لیست کلیدواژه‌ها"""
    keyword_repo = KeywordRepository(session)
    
    # محاسبه پارامترهای صفحه‌بندی
    skip = (page - 1) * page_size
    
    # دریافت کلیدواژه‌ها
    keywords = await keyword_repo.list(skip=skip, limit=page_size, active_only=active_only)
    total_count = await keyword_repo.count(active_only=active_only)
    
    # تبدیل به مدل پاسخ
    keyword_responses = [
        KeywordResponse(
            id=str(keyword.id),
            text=keyword.text,
            active=keyword.active,
            created_at=keyword.created_at
        )
        for keyword in keywords
    ]
    
    # محاسبه تعداد کل صفحات
    total_pages = (total_count + page_size - 1) // page_size
    
    return PaginatedResponse(
        items=keyword_responses,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/tweets", response_model=PaginatedResponse)
async def get_tweets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    keyword: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    """دریافت لیست توییت‌ها"""
    tweet_repo = TweetRepository(session)
    
    # محاسبه پارامترهای صفحه‌بندی
    skip = (page - 1) * page_size
    
    # دریافت توییت‌ها
    if keyword:
        tweets = await tweet_repo.get_by_keyword(
            keyword=keyword,
            skip=skip,
            limit=page_size
        )
        # در این فاز، محاسبه تعداد کل برای فیلتر کلیدواژه پیاده‌سازی نشده است
        total_count = 100  # مقدار پیش‌فرض
    else:
        tweets = await tweet_repo.list(skip=skip, limit=page_size)
        total_count = await tweet_repo.count()
    
    # تبدیل به مدل پاسخ
    tweet_responses = []
    for tweet in tweets:
        author_username = ""
        author_name = ""
        
        # دریافت اطلاعات نویسنده
        if hasattr(tweet, "user") and tweet.user:
            author_username = tweet.user.username
            author_name = tweet.user.display_name
        
        tweet_responses.append(
            TweetResponse(
                id=str(tweet.id),
                tweet_id=tweet.tweet_id,
                text=tweet.text,
                created_at=tweet.created_at,
                author_username=author_username,
                author_name=author_name,
                retweet_count=tweet.retweet_count,
                like_count=tweet.like_count,
                reply_count=tweet.reply_count,
                quote_count=tweet.quote_count,
                language=tweet.language
            )
        )
    
    # محاسبه تعداد کل صفحات
    total_pages = (total_count + page_size - 1) // page_size
    
    return PaginatedResponse(
        items=tweet_responses,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/collections", response_model=PaginatedResponse)
async def get_collections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    status: Optional[str] = None,
    collection_type: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    """دریافت لیست جمع‌آوری‌ها"""
    collection_repo = CollectionRepository(session)
    
    # تبدیل رشته به نوع شمارشی
    status_enum = None
    if status:
        try:
            status_enum = CollectionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    type_enum = None
    if collection_type:
        try:
            type_enum = CollectionType(collection_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid collection type: {collection_type}")
    
    # محاسبه پارامترهای صفحه‌بندی
    skip = (page - 1) * page_size
    
    # دریافت جمع‌آوری‌ها
    collections = await collection_repo.list(
        skip=skip,
        limit=page_size,
        status=status_enum,
        collection_type=type_enum
    )
    total_count = await collection_repo.count(status=status_enum, collection_type=type_enum)
    
    # تبدیل به مدل پاسخ
    collection_responses = [
        CollectionResponse(
            id=str(collection.id),
            name=collection.name,
            description=collection.description,
            status=collection.status.value,
            collection_type=collection.collection_type.value,
            interval_seconds=collection.interval_seconds,
            created_at=collection.created_at,
            last_run_at=collection.last_run_at,
            next_run_at=collection.next_run_at
        )
        for collection in collections
    ]
    
    # محاسبه تعداد کل صفحات
    total_pages = (total_count + page_size - 1) // page_size
    
    return PaginatedResponse(
        items=collection_responses,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.post("/collect", response_model=CollectResponse)
async def collect_tweets(request: CollectRequest):
    """جمع‌آوری فوری توییت‌ها"""
    try:
        # ایجاد کلاینت توییتر
        twitter_client = create_twitter_client()
        
        # اجرای جمع‌آوری
        collected, saved = await collect_by_keywords(
            twitter_client=twitter_client,
            keywords=request.keywords,
            query_type=request.query_type
        )
        
        return CollectResponse(
            success=True,
            collected=collected,
            saved=saved
        )
    except Exception as e:
        logger.error(f"Error collecting tweets: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))