"""
مدل‌های داده SQLAlchemy

این ماژول مدل‌های داده اصلی سیستم را تعریف می‌کند.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import (Boolean, Column, DateTime, Enum as SQLAEnum,
                        ForeignKey, Integer, JSON, String, Text)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from twitter_analysis.data.database import Base


class CollectionStatus(str, Enum):
    """وضعیت‌های ممکن برای جمع‌آوری داده"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class CollectionType(str, Enum):
    """انواع جمع‌آوری داده"""
    KEYWORD = "keyword"
    USER = "user"
    TOPIC = "topic"


class UUIDMixin:
    """میکسین برای اضافه کردن ID از نوع UUID به مدل‌ها"""
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        unique=True, 
        nullable=False
    )


class TimestampMixin:
    """میکسین برای اضافه کردن فیلدهای زمانی به مدل‌ها"""
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(Base, UUIDMixin, TimestampMixin):
    """مدل کاربر توییتر"""
    __tablename__ = "users"
    
    user_id = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    followers_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    twitter_created_at = Column(DateTime, nullable=True)
    verified = Column(Boolean, default=False)
    profile_image_url = Column(String(1024), nullable=True)
    raw_data = Column(JSON, nullable=True)
    
    # روابط
    tweets = relationship("Tweet", back_populates="user")
    
    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Tweet(Base, UUIDMixin, TimestampMixin):
    """مدل توییت"""
    __tablename__ = "tweets"
    
    tweet_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)
    retweet_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    quote_count = Column(Integer, default=0)
    view_count = Column(Integer, nullable=True)
    language = Column(String(10), nullable=True)
    source = Column(String(255), nullable=True)
    raw_data = Column(JSON, nullable=True)
    
    # روابط
    user = relationship("User", back_populates="tweets")
    tweet_keywords = relationship("TweetKeyword", back_populates="tweet")
    analyses = relationship("Analysis", back_populates="tweet")
    
    def __repr__(self) -> str:
        return f"<Tweet {self.tweet_id}>"


class Keyword(Base, UUIDMixin, TimestampMixin):
    """مدل کلیدواژه"""
    __tablename__ = "keywords"
    
    text = Column(String(255), unique=True, nullable=False, index=True)
    active = Column(Boolean, default=True)
    
    # روابط
    tweet_keywords = relationship("TweetKeyword", back_populates="keyword")
    collections = relationship("CollectionKeyword", back_populates="keyword")
    
    def __repr__(self) -> str:
        return f"<Keyword {self.text}>"


class TweetKeyword(Base, UUIDMixin):
    """جدول ارتباطی بین توییت و کلیدواژه"""
    __tablename__ = "tweet_keywords"
    
    tweet_id = Column(UUID(as_uuid=True), ForeignKey("tweets.id"), nullable=False)
    keyword_id = Column(UUID(as_uuid=True), ForeignKey("keywords.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # روابط
    tweet = relationship("Tweet", back_populates="tweet_keywords")
    keyword = relationship("Keyword", back_populates="tweet_keywords")
    
    def __repr__(self) -> str:
        return f"<TweetKeyword tweet={self.tweet_id} keyword={self.keyword_id}>"


class Collection(Base, UUIDMixin, TimestampMixin):
    """مدل جمع‌آوری داده"""
    __tablename__ = "collections"
    
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(SQLAEnum(CollectionStatus), default=CollectionStatus.ACTIVE, nullable=False)
    collection_type = Column(SQLAEnum(CollectionType), default=CollectionType.KEYWORD, nullable=False)
    parameters = Column(JSON, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    interval_seconds = Column(Integer, default=300)  # 5 دقیقه
    
    # روابط
    collection_keywords = relationship("CollectionKeyword", back_populates="collection")
    
    def __repr__(self) -> str:
        return f"<Collection {self.name} type={self.collection_type}>"


class CollectionKeyword(Base, UUIDMixin):
    """جدول ارتباطی بین جمع‌آوری و کلیدواژه"""
    __tablename__ = "collection_keywords"
    
    collection_id = Column(UUID(as_uuid=True), ForeignKey("collections.id"), nullable=False)
    keyword_id = Column(UUID(as_uuid=True), ForeignKey("keywords.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # روابط
    collection = relationship("Collection", back_populates="collection_keywords")
    keyword = relationship("Keyword", back_populates="collections")
    
    def __repr__(self) -> str:
        return f"<CollectionKeyword collection={self.collection_id} keyword={self.keyword_id}>"


class Analysis(Base, UUIDMixin, TimestampMixin):
    """مدل تحلیل داده"""
    __tablename__ = "analyses"
    
    tweet_id = Column(UUID(as_uuid=True), ForeignKey("tweets.id"), nullable=False)
    analysis_type = Column(String(50), nullable=False)
    result = Column(JSON, nullable=False)
    processed_by = Column(String(100), nullable=True)  # مدل یا روش استفاده شده برای تحلیل
    processing_time = Column(Integer, nullable=True)  # زمان پردازش به میلی‌ثانیه
    
    # روابط
    tweet = relationship("Tweet", back_populates="analyses")
    
    def __repr__(self) -> str:
        return f"<Analysis type={self.analysis_type} tweet={self.tweet_id}>"