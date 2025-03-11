"""
لایه دسترسی به داده

این ماژول واسط‌هایی برای دسترسی به داده‌های دیتابیس فراهم می‌کند.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DatabaseError
from src.data.models import (Analysis, Collection, CollectionKeyword,
                                         CollectionStatus, CollectionType,
                                         Keyword, Tweet, TweetKeyword, User)

T = TypeVar('T')


class BaseRepository:
    """پایه برای تمام مخازن داده"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def _execute_with_error_handling(self, coro: Any) -> Any:
        """اجرای یک coroutine با مدیریت خطاها"""
        try:
            return await coro
        except IntegrityError as e:
            raise DatabaseError(f"Integrity error: {str(e)}")
        except SQLAlchemyError as e:
            raise DatabaseError(f"Database error: {str(e)}")
        except Exception as e:
            raise DatabaseError(f"Unexpected error: {str(e)}")


class UserRepository(BaseRepository):
    """مخزن برای کار با کاربران"""
    
    async def create(self, **kwargs) -> User:
        """ایجاد کاربر جدید"""
        user = User(**kwargs)
        self.session.add(user)
        await self._execute_with_error_handling(self.session.flush())
        return user
    
    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """دریافت کاربر با ID"""
        query = select(User).where(User.id == user_id)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one_or_none()
    
    async def get_by_twitter_id(self, twitter_id: str) -> Optional[User]:
        """دریافت کاربر با شناسه توییتر"""
        query = select(User).where(User.user_id == twitter_id)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one_or_none()
    
    async def get_by_username(self, username: str) -> Optional[User]:
        """دریافت کاربر با نام کاربری"""
        query = select(User).where(User.username == username)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one_or_none()
    
    async def update(self, user_id: uuid.UUID, **kwargs) -> Optional[User]:
        """به‌روزرسانی کاربر"""
        query = update(User).where(User.id == user_id).values(**kwargs).returning(User)
        result = await self._execute_with_error_handling(self.session.execute(query))
        await self.session.flush()
        return result.scalar_one_or_none()
    
    async def create_or_update(self, twitter_id: str, **kwargs) -> User:
        """ایجاد یا به‌روزرسانی کاربر"""
        user = await self.get_by_twitter_id(twitter_id)
        
        if user:
            # به‌روزرسانی فیلدهای موجود
            for key, value in kwargs.items():
                setattr(user, key, value)
            await self._execute_with_error_handling(self.session.flush())
            return user
        else:
            # ایجاد کاربر جدید
            return await self.create(user_id=twitter_id, **kwargs)
    
    async def list(
        self, 
        skip: int = 0, 
        limit: int = 100, 
        filters: Optional[Dict[str, Any]] = None
    ) -> List[User]:
        """لیست کاربران با پشتیبانی از صفحه‌بندی و فیلتر"""
        query = select(User)
        
        if filters:
            for key, value in filters.items():
                if hasattr(User, key):
                    query = query.where(getattr(User, key) == value)
        
        query = query.offset(skip).limit(limit)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalars().all()
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """شمارش تعداد کاربران"""
        query = select(func.count()).select_from(User)
        
        if filters:
            for key, value in filters.items():
                if hasattr(User, key):
                    query = query.where(getattr(User, key) == value)
        
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one()


class TweetRepository(BaseRepository):
    """مخزن برای کار با توییت‌ها"""
    
    async def create(self, **kwargs) -> Tweet:
        """ایجاد توییت جدید"""
        tweet = Tweet(**kwargs)
        self.session.add(tweet)
        await self._execute_with_error_handling(self.session.flush())
        return tweet
    
    async def get_by_id(self, tweet_id: uuid.UUID) -> Optional[Tweet]:
        """دریافت توییت با ID"""
        query = select(Tweet).where(Tweet.id == tweet_id)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one_or_none()
    
    async def get_by_twitter_id(self, twitter_id: str) -> Optional[Tweet]:
        """دریافت توییت با شناسه توییتر"""
        query = select(Tweet).where(Tweet.tweet_id == twitter_id)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one_or_none()
    
    async def create_or_update(self, twitter_id: str, **kwargs) -> Tweet:
        """ایجاد یا به‌روزرسانی توییت"""
        tweet = await self.get_by_twitter_id(twitter_id)
        
        if tweet:
            # به‌روزرسانی فیلدهای موجود
            for key, value in kwargs.items():
                setattr(tweet, key, value)
            await self._execute_with_error_handling(self.session.flush())
            return tweet
        else:
            # ایجاد توییت جدید
            return await self.create(tweet_id=twitter_id, **kwargs)
    
    async def list(
        self, 
        skip: int = 0, 
        limit: int = 100, 
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        order_desc: bool = True
    ) -> List[Tweet]:
        """لیست توییت‌ها با پشتیبانی از صفحه‌بندی، فیلتر و مرتب‌سازی"""
        query = select(Tweet)
        
        if filters:
            for key, value in filters.items():
                if hasattr(Tweet, key):
                    query = query.where(getattr(Tweet, key) == value)
        
        if order_by and hasattr(Tweet, order_by):
            order_attr = getattr(Tweet, order_by)
            query = query.order_by(order_attr.desc() if order_desc else order_attr)
        else:
            # مرتب‌سازی پیش‌فرض بر اساس زمان ایجاد
            query = query.order_by(Tweet.created_at.desc() if order_desc else Tweet.created_at)
        
        query = query.offset(skip).limit(limit)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalars().all()
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """شمارش تعداد توییت‌ها"""
        query = select(func.count()).select_from(Tweet)
        
        if filters:
            for key, value in filters.items():
                if hasattr(Tweet, key):
                    query = query.where(getattr(Tweet, key) == value)
        
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one()
    
    async def get_by_keyword(
        self, 
        keyword: str, 
        skip: int = 0, 
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = True
    ) -> List[Tweet]:
        """دریافت توییت‌ها بر اساس کلیدواژه"""
        # پیوند توییت‌ها با کلیدواژه‌ها
        join_query = (
            select(Tweet)
            .join(TweetKeyword, Tweet.id == TweetKeyword.tweet_id)
            .join(Keyword, TweetKeyword.keyword_id == Keyword.id)
            .where(Keyword.text == keyword)
        )
        
        if order_by and hasattr(Tweet, order_by):
            order_attr = getattr(Tweet, order_by)
            join_query = join_query.order_by(order_attr.desc() if order_desc else order_attr)
        else:
            # مرتب‌سازی پیش‌فرض بر اساس زمان ایجاد
            join_query = join_query.order_by(Tweet.created_at.desc() if order_desc else Tweet.created_at)
        
        join_query = join_query.offset(skip).limit(limit)
        result = await self._execute_with_error_handling(self.session.execute(join_query))
        return result.scalars().all()


class KeywordRepository(BaseRepository):
    """مخزن برای کار با کلیدواژه‌ها"""
    
    async def create(self, text: str, active: bool = True) -> Keyword:
        """ایجاد کلیدواژه جدید"""
        keyword = Keyword(text=text, active=active)
        self.session.add(keyword)
        await self._execute_with_error_handling(self.session.flush())
        return keyword
    
    async def get_by_id(self, keyword_id: uuid.UUID) -> Optional[Keyword]:
        """دریافت کلیدواژه با ID"""
        query = select(Keyword).where(Keyword.id == keyword_id)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one_or_none()
    
    async def get_by_text(self, text: str) -> Optional[Keyword]:
        """دریافت کلیدواژه با متن"""
        query = select(Keyword).where(Keyword.text == text)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one_or_none()
    
    async def get_or_create(self, text: str, active: bool = True) -> Keyword:
        """دریافت کلیدواژه موجود یا ایجاد جدید"""
        keyword = await self.get_by_text(text)
        
        if keyword:
            # اگر وضعیت فعال کلیدواژه تغییر کرده باشد، آن را به‌روزرسانی می‌کنیم
            if keyword.active != active:
                keyword.active = active
                await self._execute_with_error_handling(self.session.flush())
            return keyword
        else:
            # ایجاد کلیدواژه جدید
            return await self.create(text=text, active=active)
    
    async def list(
        self, 
        skip: int = 0, 
        limit: int = 100, 
        active_only: bool = False
    ) -> List[Keyword]:
        """لیست کلیدواژه‌ها با پشتیبانی از صفحه‌بندی و فیلتر وضعیت فعال"""
        query = select(Keyword)
        
        if active_only:
            query = query.where(Keyword.active == True)
        
        query = query.order_by(Keyword.text).offset(skip).limit(limit)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalars().all()
    
    async def count(self, active_only: bool = False) -> int:
        """شمارش تعداد کلیدواژه‌ها"""
        query = select(func.count()).select_from(Keyword)
        
        if active_only:
            query = query.where(Keyword.active == True)
        
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one()
    
    async def associate_with_tweet(self, keyword_id: uuid.UUID, tweet_id: uuid.UUID) -> TweetKeyword:
        """ایجاد ارتباط بین کلیدواژه و توییت"""
        # بررسی عدم وجود ارتباط قبلی
        query = select(TweetKeyword).where(
            TweetKeyword.keyword_id == keyword_id,
            TweetKeyword.tweet_id == tweet_id
        )
        result = await self._execute_with_error_handling(self.session.execute(query))
        
        if result.scalar_one_or_none():
            # ارتباط قبلاً وجود دارد
            return result.scalar_one()
        
        # ایجاد ارتباط جدید
        tweet_keyword = TweetKeyword(keyword_id=keyword_id, tweet_id=tweet_id)
        self.session.add(tweet_keyword)
        await self._execute_with_error_handling(self.session.flush())
        return tweet_keyword


class CollectionRepository(BaseRepository):
    """مخزن برای کار با جمع‌آوری‌ها"""
    
    async def create(
        self, 
        name: str, 
        collection_type: CollectionType, 
        **kwargs
    ) -> Collection:
        """ایجاد جمع‌آوری جدید"""
        collection = Collection(
            name=name,
            collection_type=collection_type,
            **kwargs
        )
        self.session.add(collection)
        await self._execute_with_error_handling(self.session.flush())
        return collection
    
    async def get_by_id(self, collection_id: uuid.UUID) -> Optional[Collection]:
        """دریافت جمع‌آوری با ID"""
        query = select(Collection).where(Collection.id == collection_id)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one_or_none()
    
    async def update(self, collection_id: uuid.UUID, **kwargs) -> Optional[Collection]:
        """به‌روزرسانی جمع‌آوری"""
        query = update(Collection).where(Collection.id == collection_id).values(**kwargs).returning(Collection)
        result = await self._execute_with_error_handling(self.session.execute(query))
        await self.session.flush()
        return result.scalar_one_or_none()
    
    async def list(
        self, 
        skip: int = 0, 
        limit: int = 100, 
        status: Optional[CollectionStatus] = None,
        collection_type: Optional[CollectionType] = None
    ) -> List[Collection]:
        """لیست جمع‌آوری‌ها با پشتیبانی از صفحه‌بندی و فیلتر"""
        query = select(Collection)
        
        if status:
            query = query.where(Collection.status == status)
        
        if collection_type:
            query = query.where(Collection.collection_type == collection_type)
        
        query = query.order_by(Collection.created_at.desc()).offset(skip).limit(limit)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalars().all()
    
    async def count(
        self, 
        status: Optional[CollectionStatus] = None,
        collection_type: Optional[CollectionType] = None
    ) -> int:
        """شمارش تعداد جمع‌آوری‌ها"""
        query = select(func.count()).select_from(Collection)
        
        if status:
            query = query.where(Collection.status == status)
        
        if collection_type:
            query = query.where(Collection.collection_type == collection_type)
        
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one()
    
    async def get_due_collections(self) -> List[Collection]:
        """دریافت جمع‌آوری‌هایی که زمان اجرای آن‌ها فرا رسیده است"""
        now = datetime.utcnow()
        query = (
            select(Collection)
            .where(Collection.status == CollectionStatus.ACTIVE)
            .where(
                (Collection.next_run_at <= now) |  # زمان اجرای بعدی گذشته
                (Collection.next_run_at == None)    # یا هنوز اجرا نشده
            )
        )
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalars().all()
    
    async def add_keyword(self, collection_id: uuid.UUID, keyword_id: uuid.UUID) -> CollectionKeyword:
        """اضافه کردن کلیدواژه به جمع‌آوری"""
        # بررسی عدم وجود ارتباط قبلی
        query = select(CollectionKeyword).where(
            CollectionKeyword.collection_id == collection_id,
            CollectionKeyword.keyword_id == keyword_id
        )
        result = await self._execute_with_error_handling(self.session.execute(query))
        
        if result.scalar_one_or_none():
            # ارتباط قبلاً وجود دارد
            return result.scalar_one()
        
        # ایجاد ارتباط جدید
        collection_keyword = CollectionKeyword(collection_id=collection_id, keyword_id=keyword_id)
        self.session.add(collection_keyword)
        await self._execute_with_error_handling(self.session.flush())
        return collection_keyword
    
    async def remove_keyword(self, collection_id: uuid.UUID, keyword_id: uuid.UUID) -> bool:
        """حذف کلیدواژه از جمع‌آوری"""
        query = delete(CollectionKeyword).where(
            CollectionKeyword.collection_id == collection_id,
            CollectionKeyword.keyword_id == keyword_id
        )
        result = await self._execute_with_error_handling(self.session.execute(query))
        await self.session.flush()
        return result.rowcount > 0
    
    async def get_keywords(self, collection_id: uuid.UUID) -> List[Keyword]:
        """دریافت کلیدواژه‌های یک جمع‌آوری"""
        query = (
            select(Keyword)
            .join(CollectionKeyword, Keyword.id == CollectionKeyword.keyword_id)
            .where(CollectionKeyword.collection_id == collection_id)
        )
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalars().all()


class AnalysisRepository(BaseRepository):
    """مخزن برای کار با تحلیل‌ها"""
    
    async def create(self, tweet_id: uuid.UUID, analysis_type: str, result: Dict[str, Any], **kwargs) -> Analysis:
        """ایجاد تحلیل جدید"""
        analysis = Analysis(
            tweet_id=tweet_id,
            analysis_type=analysis_type,
            result=result,
            **kwargs
        )
        self.session.add(analysis)
        await self._execute_with_error_handling(self.session.flush())
        return analysis
    
    async def get_by_id(self, analysis_id: uuid.UUID) -> Optional[Analysis]:
        """دریافت تحلیل با ID"""
        query = select(Analysis).where(Analysis.id == analysis_id)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one_or_none()
    
    async def get_by_tweet_and_type(self, tweet_id: uuid.UUID, analysis_type: str) -> Optional[Analysis]:
        """دریافت تحلیل برای یک توییت و نوع خاص"""
        query = select(Analysis).where(
            Analysis.tweet_id == tweet_id,
            Analysis.analysis_type == analysis_type
        )
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalar_one_or_none()
    
    async def list_by_tweet(self, tweet_id: uuid.UUID) -> List[Analysis]:
        """دریافت تمام تحلیل‌های یک توییت"""
        query = select(Analysis).where(Analysis.tweet_id == tweet_id)
        result = await self._execute_with_error_handling(self.session.execute(query))
        return result.scalars().all()
    
    async def create_or_update(
        self, 
        tweet_id: uuid.UUID, 
        analysis_type: str, 
        result: Dict[str, Any], 
        **kwargs
    ) -> Analysis:
        """ایجاد یا به‌روزرسانی تحلیل"""
        analysis = await self.get_by_tweet_and_type(tweet_id, analysis_type)
        
        if analysis:
            # به‌روزرسانی تحلیل موجود
            analysis.result = result
            analysis.updated_at = datetime.utcnow()
            
            for key, value in kwargs.items():
                setattr(analysis, key, value)
                
            await self._execute_with_error_handling(self.session.flush())
            return analysis
        else:
            # ایجاد تحلیل جدید
            return await self.create(tweet_id, analysis_type, result, **kwargs)