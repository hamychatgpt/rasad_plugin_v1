"""
پیاده‌سازی کلاینت Twitter API

این ماژول کلاینت Twitter API را بر اساس مستندات API پیاده‌سازی می‌کند.
"""

import asyncio
import json
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
from pydantic import ValidationError

from twitter_analysis.api.interfaces import (SearchParameters, TweetData,
                                            TwitterAPIClient, UserData)
from twitter_analysis.config.settings import settings
from twitter_analysis.core.exceptions import (RateLimitError, TwitterAPIError,
                                             ValidationError as AppValidationError)


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
        """اطمینان از وجود جلسه HTTP"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={"X-API-Key": self.api_key}
            )
    
    async def _close_session(self) -> None:
        """بستن جلسه HTTP"""
        if self.session is not None and not self.session.closed:
            await self.session.close()
    
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
        
        remaining = int(rate_info["remaining"])
        reset_time = float(rate_info["reset"])
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
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """اجرای یک درخواست HTTP با مدیریت محدودیت نرخ و بازتلاش"""
        await self._ensure_session()
        assert self.session is not None
        
        url = f"{self.base_url}{endpoint}"
        last_exception = None
        
        for attempt in range(self.max_attempts):
            # بررسی محدودیت نرخ
            can_request, wait_time = self._check_rate_limit(endpoint)
            if not can_request and wait_time is not None:
                if attempt < self.max_attempts - 1:  # بازتلاش در تلاش بعدی
                    await asyncio.sleep(wait_time)
                else:  # تلاش‌های ما به پایان رسید
                    raise RateLimitError(
                        message=f"Rate limit exceeded for endpoint {endpoint}",
                        retry_after=int(wait_time),
                        status_code=429
                    )
            
            try:
                async with getattr(self.session, method.lower())(url, **kwargs) as response:
                    # به‌روزرسانی محدودیت نرخ
                    self._update_rate_limits(endpoint, response.headers)
                    
                    # بررسی کد وضعیت
                    if response.status == 429:  # محدودیت نرخ
                        retry_after = int(response.headers.get("Retry-After", "60"))
                        self.rate_limits[endpoint] = {
                            "limit": 0,
                            "remaining": 0,
                            "reset": time.time() + retry_after
                        }
                        if attempt < self.max_attempts - 1:
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            raise RateLimitError(
                                message="Rate limit exceeded",
                                retry_after=retry_after,
                                status_code=429,
                                response_body=await response.text()
                            )
                    
                    # خطاهای دیگر
                    if response.status >= 400:
                        response_text = await response.text()
                        if attempt < self.max_attempts - 1:
                            # عقب‌نشینی نمایی
                            backoff = self._calculate_backoff(attempt)
                            await asyncio.sleep(backoff)
                            continue
                        else:
                            raise TwitterAPIError(
                                message=f"Twitter API error: {response.status}",
                                status_code=response.status,
                                response_body=response_text
                            )
                    
                    # درخواست موفق
                    return await response.json()
            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < self.max_attempts - 1:
                    backoff = self._calculate_backoff(attempt)
                    await asyncio.sleep(backoff)
                    continue
        
        # اگر تمام تلاش‌ها شکست خورد
        raise TwitterAPIError(
            message=f"Failed after {self.max_attempts} attempts: {str(last_exception)}"
        )
    
    def _parse_tweet_data(self, tweet_data: Dict[str, Any]) -> TweetData:
        """تبدیل داده خام توییت به مدل TweetData"""
        try:
            author = tweet_data.get("author", {})
            
            return TweetData(
                tweet_id=tweet_data.get("id", ""),
                text=tweet_data.get("text", ""),
                created_at=datetime.strptime(tweet_data.get("createdAt", ""), "%a %b %d %H:%M:%S %z %Y") 
                           if "createdAt" in tweet_data else datetime.now(),
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
            raise AppValidationError(
                message=f"Error parsing tweet data: {str(e)}",
                details={"tweet_data": tweet_data}
            )
    
    def _parse_user_data(self, user_data: Dict[str, Any]) -> UserData:
        """تبدیل داده خام کاربر به مدل UserData"""
        try:
            return UserData(
                user_id=user_data.get("id", ""),
                username=user_data.get("userName", ""),
                display_name=user_data.get("name", ""),
                description=user_data.get("description"),
                followers_count=user_data.get("followers", 0),
                following_count=user_data.get("following", 0),
                created_at=datetime.strptime(user_data.get("createdAt", ""), "%a %b %d %H:%M:%S %z %Y")
                          if "createdAt" in user_data else datetime.now(),
                verified=user_data.get("isBlueVerified", False),
                profile_image_url=user_data.get("profilePicture"),
                raw_data=user_data
            )
        except (ValidationError, ValueError) as e:
            raise AppValidationError(
                message=f"Error parsing user data: {str(e)}",
                details={"user_data": user_data}
            )
    
    async def search_tweets(self, params: SearchParameters) -> List[TweetData]:
        """جستجوی توییت‌ها بر اساس پارامترهای داده شده"""
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
        return [self._parse_tweet_data(tweet) for tweet in tweets]
    
    async def get_user_info(self, username: str) -> UserData:
        """دریافت اطلاعات کاربر با نام کاربری"""
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
        return [self._parse_tweet_data(tweet) for tweet in tweets]
    
    async def get_tweets_by_ids(self, tweet_ids: List[str]) -> List[TweetData]:
        """دریافت توییت‌ها با شناسه‌های داده شده"""
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
        return [self._parse_tweet_data(tweet) for tweet in tweets]
    
    async def __aenter__(self) -> "TwitterClient":
        """مدیریت متن با استفاده از async with"""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """پاکسازی منابع هنگام خروج از متن"""
        await self._close_session()


def create_twitter_client() -> TwitterClient:
    """تابع سازنده برای ایجاد نمونه از کلاینت توییتر"""
    return TwitterClient(
        api_key=settings.twitter_api.api_key,
        base_url=settings.twitter_api.base_url
    )