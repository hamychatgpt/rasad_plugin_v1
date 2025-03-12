"""
پیاده‌سازی کلاینت Twitter API

این ماژول کلاینت Twitter API را بر اساس مستندات API پیاده‌سازی می‌کند.
"""
import os
import asyncio
import json
import logging
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union, cast

import aiohttp
from pydantic import ValidationError

from src.api.interfaces import (SearchParameters, TweetData,
                               TwitterAPIClient, UserData)
from src.config.settings import settings
from src.core.exceptions import (RateLimitError, TwitterAPIError,
                                ValidationError as AppValidationError)

logger = logging.getLogger(__name__)


class MockTwitterClient(TwitterAPIClient):
    """پیاده‌سازی شبیه‌سازی شده Twitter API برای زمانی که API key نامعتبر است"""
    
    async def search_tweets(self, params: SearchParameters) -> List[TweetData]:
        """شبیه‌سازی جستجوی توییت‌ها"""
        logger.warning(f"Using mock client for search_tweets with query: {params.query}")
        return []
    
    async def get_user_info(self, username: str) -> UserData:
        """شبیه‌سازی دریافت اطلاعات کاربر"""
        logger.warning(f"Using mock client for get_user_info with username: {username}")
        # ساخت یک کاربر شبیه‌سازی شده
        return UserData(
            user_id="mock_user_id",
            username=username,
            display_name=f"Mock User ({username})",
            description="This is a mock user for testing",
            followers_count=0,
            following_count=0,
            created_at=datetime.now(),
            verified=False,
            profile_image_url=None,
            raw_data={}
        )
    
    async def get_user_tweets(
        self, 
        user_id: str, 
        include_replies: bool = False, 
        cursor: Optional[str] = None
    ) -> List[TweetData]:
        """شبیه‌سازی دریافت توییت‌های کاربر"""
        logger.warning(f"Using mock client for get_user_tweets with user_id: {user_id}")
        return []
    
    async def get_tweets_by_ids(self, tweet_ids: List[str]) -> List[TweetData]:
        """شبیه‌سازی دریافت توییت‌ها با شناسه"""
        logger.warning(f"Using mock client for get_tweets_by_ids with {len(tweet_ids)} ids")
        return []


class TwitterClient(TwitterAPIClient):
    """پیاده‌سازی کلاینت Twitter API"""
    
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        
        # تنظیمات محدودیت نرخ
        self.rate_limits: Dict[str, Dict[str, Union[int, float]]] = {
            "default": {
                "limit": settings.twitter_api.default_qps,
                "remaining": settings.twitter_api.default_qps,
                "reset": time.time() + 1
            }
        }
        
        # تنظیمات بازتلاش
        self.max_attempts = settings.twitter_api.max_attempts
        self.initial_delay = settings.twitter_api.initial_delay
        self.exponential_factor = settings.twitter_api.exponential_factor
        self.jitter = settings.twitter_api.jitter
    
    async def _ensure_session(self) -> None:
        """اطمینان از وجود جلسه HTTP با تنظیم صحیح هدرها"""
        if self.session is None or self.session.closed:
            headers = {
                "X-API-Key": self.api_key,
                "x-api-key": self.api_key,  # اضافه کردن هر دو فرمت احتمالی هدر
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            self.session = aiohttp.ClientSession(headers=headers)
            logger.debug(f"Created new HTTP session with headers: {headers}")
    
    async def _close_session(self) -> None:
        """بستن جلسه HTTP"""
        if self.session is not None and not self.session.closed:
            await self.session.close()
            logger.debug("HTTP session closed")
    
    def _update_rate_limits(self, endpoint: str, headers: Dict[str, str]) -> None:
        """به‌روزرسانی اطلاعات محدودیت نرخ از هدرهای پاسخ"""
        limit = int(headers.get("X-Rate-Limit-Limit", "0"))
        remaining = int(headers.get("X-Rate-Limit-Remaining", "0"))
        reset = float(headers.get("X-Rate-Limit-Reset", "0"))
        
        if limit > 0:
            self.rate_limits[endpoint] = {
                "limit": limit,
                "remaining": remaining,
                "reset": reset
            }
    
    def _check_rate_limit(self, endpoint: str) -> Tuple[bool, Optional[float]]:
        """بررسی محدودیت نرخ برای یک نقطه پایانی"""
        rate_info = self.rate_limits.get(endpoint, self.rate_limits["default"])
        
        remaining = int(cast(int, rate_info["remaining"]))
        reset_time = float(cast(float, rate_info["reset"]))
        current_time = time.time()
        
        if remaining <= 0 and current_time < reset_time:
            wait_time = reset_time - current_time
            return False, wait_time
        
        return True, None
    
    def _calculate_backoff(self, attempt: int) -> float:
        """محاسبه زمان انتظار برای بازتلاش"""
        delay = self.initial_delay * (self.exponential_factor ** attempt)
        jitter_amount = delay * self.jitter
        return delay + random.uniform(-jitter_amount, jitter_amount)
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """اجرای یک درخواست HTTP با مدیریت محدودیت نرخ و بازتلاش"""
        await self._ensure_session()
        assert self.session is not None
        
        url = f"{self.base_url}{endpoint}"
        last_exception = None
        
        # لیست کدهای وضعیت قابل بازتلاش
        retryable_status_codes = {429, 500, 502, 503, 504}
        
        # اطمینان از اینکه API key در هدرها وجود دارد
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        
        # اضافه کردن API key به هدرهای درخواست برای اطمینان
        kwargs['headers'].update({
            "X-API-Key": self.api_key,
            "x-api-key": self.api_key
        })
        
        logger.debug(f"Making request to {url} with method {method}")
        
        for attempt in range(self.max_attempts):
            # بررسی محدودیت نرخ
            can_request, wait_time = self._check_rate_limit(endpoint)
            if not can_request and wait_time is not None:
                if attempt < self.max_attempts - 1:  # بازتلاش در تلاش بعدی
                    logger.info(f"Rate limit hit, waiting {wait_time:.2f}s before retry ({attempt+1}/{self.max_attempts})")
                    await asyncio.sleep(wait_time)
                else:  # تلاش‌های ما به پایان رسید
                    await self._close_session()  # بستن جلسه قبل از خطا
                    raise RateLimitError(
                        message=f"Rate limit exceeded for endpoint {endpoint}",
                        retry_after=int(wait_time),
                        status_code=429
                    )
            
            try:
                method_func = getattr(self.session, method.lower())
                async with method_func(url, **kwargs) as response:
                    # به‌روزرسانی محدودیت نرخ
                    self._update_rate_limits(endpoint, response.headers)
                    
                    response_text = await response.text()
                    logger.debug(f"Received response: HTTP {response.status}, body length: {len(response_text)}")
                    
                    # بررسی خطای احراز هویت که نیاز به بازتلاش ندارد
                    if response.status == 401:
                        logger.error(f"Authentication error (HTTP 401): {response_text[:200]}")
                        await self._close_session()
                        raise TwitterAPIError(
                            message=f"Twitter API authentication error: API key is invalid or missing",
                            status_code=401,
                            response_body=response_text
                        )
                    
                    # بررسی کد وضعیت
                    if response.status == 429:  # محدودیت نرخ
                        retry_after = int(response.headers.get("Retry-After", "60"))
                        self.rate_limits[endpoint] = {
                            "limit": 0,
                            "remaining": 0,
                            "reset": time.time() + retry_after
                        }
                        logger.warning(f"Rate limit exceeded (HTTP 429), retry after {retry_after}s")
                        if attempt < self.max_attempts - 1:
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            await self._close_session()  # بستن جلسه قبل از خطا
                            raise RateLimitError(
                                message="Rate limit exceeded",
                                retry_after=retry_after,
                                status_code=429,
                                response_body=response_text
                            )
                    
                    # خطاهای قابل بازتلاش
                    elif response.status in retryable_status_codes:
                        logger.warning(f"Retryable error: HTTP {response.status} - {response_text[:100]}...")
                        if attempt < self.max_attempts - 1:
                            backoff = self._calculate_backoff(attempt)
                            logger.info(f"Retrying in {backoff:.2f}s (attempt {attempt+1}/{self.max_attempts})")
                            await asyncio.sleep(backoff)
                            continue
                        else:
                            await self._close_session()
                            raise TwitterAPIError(
                                message=f"Twitter API error after max retries: HTTP {response.status}",
                                status_code=response.status,
                                response_body=response_text
                            )
                    
                    # خطاهای غیرقابل بازتلاش
                    elif response.status >= 400:
                        logger.error(f"Non-retryable error: HTTP {response.status} - {response_text[:100]}...")
                        await self._close_session()
                        raise TwitterAPIError(
                            message=f"Twitter API error: HTTP {response.status}",
                            status_code=response.status,
                            response_body=response_text
                        )
                    
                    # درخواست موفق
                    try:
                        return json.loads(response_text)
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON response: {response_text[:100]}...")
                        raise TwitterAPIError(
                            message="Invalid JSON response from Twitter API",
                            status_code=response.status,
                            response_body=response_text
                        )
                
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Network error: {str(e)}")
                last_exception = e
                if attempt < self.max_attempts - 1:
                    backoff = self._calculate_backoff(attempt)
                    logger.info(f"Retrying in {backoff:.2f}s (attempt {attempt+1}/{self.max_attempts})")
                    await asyncio.sleep(backoff)
                    continue
                else:
                    logger.error(f"Network error after max retries: {str(e)}")
        
        # اگر تمام تلاش‌ها شکست خورد، جلسه را ببندیم
        await self._close_session()
        raise TwitterAPIError(
            message=f"Failed after {self.max_attempts} attempts: {str(last_exception)}",
            details={"error": str(last_exception)}
        )
    
    def _parse_tweet_data(self, tweet_data: Dict[str, Any]) -> TweetData:
        """تبدیل داده خام توییت به مدل TweetData"""
        try:
            author = tweet_data.get("author", {})
            
            # تبدیل تاریخ با مدیریت خطا
            created_at = datetime.now()
            if "createdAt" in tweet_data:
                try:
                    created_at = datetime.strptime(
                        tweet_data.get("createdAt", ""), 
                        "%a %b %d %H:%M:%S %z %Y"
                    )
                except ValueError as e:
                    logger.warning(f"Invalid date format: {tweet_data.get('createdAt')} - {str(e)}")
            
            return TweetData(
                tweet_id=tweet_data.get("id", ""),
                text=tweet_data.get("text", ""),
                created_at=created_at,
                author_id=author.get("id", ""),
                author_username=author.get("userName", ""),
                author_name=author.get("name", ""),
                retweet_count=tweet_data.get("retweetCount", 0),
                reply_count=tweet_data.get("replyCount", 0),
                like_count=tweet_data.get("likeCount", 0),
                quote_count=tweet_data.get("quoteCount", 0),
                view_count=tweet_data.get("viewCount"),
                language=tweet_data.get("lang"),
                source=tweet_data.get("source"),
                raw_data=tweet_data
            )
        except (ValidationError, ValueError) as e:
            logger.error(f"Error parsing tweet data: {str(e)}")
            raise AppValidationError(
                message=f"Error parsing tweet data: {str(e)}",
                details={"tweet_data": tweet_data}
            )
    
    def _parse_user_data(self, user_data: Dict[str, Any]) -> UserData:
        """تبدیل داده خام کاربر به مدل UserData"""
        try:
            # تبدیل تاریخ با مدیریت خطا
            created_at = datetime.now()
            if "createdAt" in user_data:
                try:
                    created_at = datetime.strptime(
                        user_data.get("createdAt", ""), 
                        "%a %b %d %H:%M:%S %z %Y"
                    )
                except ValueError as e:
                    logger.warning(f"Invalid user date format: {user_data.get('createdAt')} - {str(e)}")
            
            return UserData(
                user_id=user_data.get("id", ""),
                username=user_data.get("userName", ""),
                display_name=user_data.get("name", ""),
                description=user_data.get("description"),
                followers_count=user_data.get("followers", 0),
                following_count=user_data.get("following", 0),
                created_at=created_at,
                verified=user_data.get("isBlueVerified", False),
                profile_image_url=user_data.get("profilePicture"),
                raw_data=user_data
            )
        except (ValidationError, ValueError) as e:
            logger.error(f"Error parsing user data: {str(e)}")
            raise AppValidationError(
                message=f"Error parsing user data: {str(e)}",
                details={"user_data": user_data}
            )
    
    async def search_tweets(self, params: SearchParameters) -> List[TweetData]:
        """جستجوی توییت‌ها بر اساس پارامترهای داده شده"""
        logger.info(f"Searching tweets with query: {params.query}, type: {params.query_type}")
        
        query_params = {
            "query": params.query,
            "queryType": params.query_type
        }
        
        if params.cursor:
            query_params["cursor"] = params.cursor
        
        response = await self._make_request(
            "GET", 
            "/twitter/tweet/advanced_search", 
            params=query_params
        )
        
        # بررسی وضعیت پاسخ
        if response.get("status") != "success":
            raise TwitterAPIError(
                message=f"Twitter API error: {response.get('msg', 'Unknown error')}",
                details={"response": response}
            )
        
        # استخراج توییت‌ها
        tweets = response.get("data", {}).get("list", [])
        result = [self._parse_tweet_data(tweet) for tweet in tweets]
        
        logger.info(f"Found {len(result)} tweets for query: {params.query}")
        return result
    
    async def get_user_info(self, username: str) -> UserData:
        """دریافت اطلاعات کاربر با نام کاربری"""
        logger.info(f"Getting user info for username: {username}")
        
        response = await self._make_request(
            "GET",
            "/twitter/user/info",
            params={"userName": username}
        )
        
        # بررسی وضعیت پاسخ
        if response.get("status") != "success":
            raise TwitterAPIError(
                message=f"Twitter API error: {response.get('msg', 'Unknown error')}",
                details={"response": response}
            )
        
        # استخراج اطلاعات کاربر
        user_data = response.get("data", {})
        return self._parse_user_data(user_data)
    
    async def get_user_tweets(
        self, 
        user_id: str, 
        include_replies: bool = False, 
        cursor: Optional[str] = None
    ) -> List[TweetData]:
        """دریافت توییت‌های اخیر یک کاربر"""
        logger.info(f"Getting tweets for user_id: {user_id}, include_replies: {include_replies}")
        
        query_params = {
            "userId": user_id,
            "includeReplies": str(include_replies).lower()
        }
        
        if cursor:
            query_params["cursor"] = cursor
        
        response = await self._make_request(
            "GET",
            "/twitter/user/last_tweets",
            params=query_params
        )
        
        # بررسی وضعیت پاسخ
        if response.get("status") != "success":
            raise TwitterAPIError(
                message=f"Twitter API error: {response.get('msg', 'Unknown error')}",
                details={"response": response}
            )
        
        # استخراج توییت‌ها
        tweets = response.get("data", {}).get("list", [])
        result = [self._parse_tweet_data(tweet) for tweet in tweets]
        
        logger.info(f"Found {len(result)} tweets for user_id: {user_id}")
        return result
    
    async def get_tweets_by_ids(self, tweet_ids: List[str]) -> List[TweetData]:
        """دریافت توییت‌ها با شناسه‌های داده شده"""
        logger.info(f"Getting tweets by ids: {len(tweet_ids)} ids")
        
        response = await self._make_request(
            "GET",
            "/twitter/tweets",
            params={"tweet_ids": ",".join(tweet_ids)}
        )
        
        # بررسی وضعیت پاسخ
        if response.get("status") != "success":
            raise TwitterAPIError(
                message=f"Twitter API error: {response.get('msg', 'Unknown error')}",
                details={"response": response}
            )
        
        # استخراج توییت‌ها
        tweets = response.get("data", [])
        result = [self._parse_tweet_data(tweet) for tweet in tweets]
        
        logger.info(f"Found {len(result)} tweets from {len(tweet_ids)} requested ids")
        return result
    
    async def __aenter__(self) -> "TwitterClient":
        """مدیریت متن با استفاده از async with"""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """پاکسازی منابع هنگام خروج از متن"""
        await self._close_session()

def create_twitter_client() -> TwitterAPIClient:
    """تابع سازنده برای ایجاد نمونه از کلاینت توییتر"""
    # Чтение напрямую из переменных окружения вместо settings
    api_key = os.environ.get("TWITTER_API_KEY", "")
    base_url = settings.twitter_api.base_url
    
    if not api_key:
        logger.warning("Twitter API key is missing or invalid. Using mock client that will return empty results.")
        return MockTwitterClient()
    
    logger.info(f"Creating real Twitter client with API key: {api_key[:4]}...")
    return TwitterClient(
        api_key=api_key,
        base_url=base_url
    )