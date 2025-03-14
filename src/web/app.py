"""
برنامه وب FastAPI

این ماژول برنامه FastAPI را راه‌اندازی می‌کند.
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from src.api.twitter import create_twitter_client
from src.collector.keyword import collect_by_keywords
from src.config.settings import settings
from src.core.di import container
from src.core.exceptions import TwitterAnalysisError
from src.core.plugin import PluginManager, plugin_manager
from src.data.database import create_tables, get_db_session
from src.data.models import Collection, CollectionStatus, CollectionType
from src.data.repositories import (CollectionRepository, KeywordRepository,
                                  TweetRepository, UserRepository)
from src.processor.pipeline import TweetProcessingPipeline
from src.web.api import router as api_router

logger = logging.getLogger(__name__)

# ایجاد برنامه FastAPI
app = FastAPI(
    title="Twitter Analysis System",
    description="سیستم رصد و تحلیل توییتر",
    version="0.1.0"
)

# پیکربندی CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# افزودن middleware برای مدیریت جلسه‌ها
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key
)

# تنظیم مسیرهای استاتیک و قالب‌ها
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# بررسی وجود مسیرها
if not STATIC_DIR.exists():
    logger.warning(f"Static directory not found at {STATIC_DIR}")

if not TEMPLATES_DIR.exists():
    logger.warning(f"Templates directory not found at {TEMPLATES_DIR}")

# ثبت فایل‌های استاتیک
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# تنظیم موتور قالب
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals.update({
    "max": max,
    "min": min,
    "len": len,
    "str": str,
    "hasattr": hasattr,
    "isinstance": isinstance,
    "list": list,
    "dict": dict
})
# افزودن روتر API
app.include_router(api_router, prefix="/api")

# تعریف مدل‌های پایدانتیک برای API
class KeywordCreate(BaseModel):
    """مدل ایجاد کلیدواژه"""
    text: str
    active: bool = True


class CollectionCreate(BaseModel):
    """مدل ایجاد جمع‌آوری"""
    name: str
    description: Optional[str] = None
    status: CollectionStatus = CollectionStatus.ACTIVE
    collection_type: CollectionType = CollectionType.KEYWORD
    interval_seconds: int = 300
    keywords: List[str] = []


async def get_session() -> AsyncSession:
    """تابع وابستگی برای دریافت جلسه دیتابیس"""
    async with get_db_session() as session:
        yield session


@app.on_event("startup")
async def startup_event():
    """رویداد راه‌اندازی برنامه"""
    logger.info("Application starting up...")
    try:
        # ایجاد جدول‌های دیتابیس
        await create_tables()
        logger.info("Database tables created or verified")
        
        try:
            # کشف و راه‌اندازی پلاگین‌ها
            plugin_manager.discover_plugins("src.collector")
            plugin_manager.initialize_all()
            logger.info("Plugins initialized")
        except Exception as e:
            logger.error(f"Error initializing plugins: {e}", exc_info=True)
            # ادامه کار برنامه حتی در صورت خطا در پلاگین‌ها
        
    except Exception as e:
        logger.error(f"Critical error during startup: {e}", exc_info=True)
        # بازگشت خطا بدون خروج از برنامه
        # در حالت توسعه می‌توان برنامه را متوقف کرد اما در محیط تولید ادامه می‌دهیم
        if os.environ.get("APP_ENV") == "development":
            import sys
            sys.exit(1)


@app.on_event("shutdown")
async def shutdown_event():
    """رویداد خاموش کردن برنامه"""
    try:
        # خاموش کردن پلاگین‌ها
        plugin_manager.shutdown_all()
        logger.info("Plugins shutdown")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}", exc_info=True)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """صفحه اصلی"""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "سیستم رصد و تحلیل توییتر"}
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    """داشبورد مدیریت"""
    # دریافت آمار کلی
    tweet_repo = TweetRepository(session)
    user_repo = UserRepository(session)
    keyword_repo = KeywordRepository(session)
    collection_repo = CollectionRepository(session)
    
    tweet_count = await tweet_repo.count()
    user_count = await user_repo.count()
    keyword_count = await keyword_repo.count()
    collection_count = await collection_repo.count()
    
    # دریافت آخرین توییت‌ها
    latest_tweets = await tweet_repo.list(limit=10)
    
    # دریافت کلیدواژه‌های فعال
    active_keywords = await keyword_repo.list(active_only=True)
    
    # دریافت جمع‌آوری‌های فعال
    active_collections = await collection_repo.list(status=CollectionStatus.ACTIVE)
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "داشبورد مدیریت",
            "stats": {
                "tweet_count": tweet_count,
                "user_count": user_count,
                "keyword_count": keyword_count,
                "collection_count": collection_count
            },
            "latest_tweets": latest_tweets,
            "active_keywords": active_keywords,
            "active_collections": active_collections
        }
    )


@app.get("/keywords", response_class=HTMLResponse)
async def keywords_page(
    request: Request, 
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    session: AsyncSession = Depends(get_session)
):
    """صفحه مدیریت کلیدواژه‌ها"""
    keyword_repo = KeywordRepository(session)
    
    # محاسبه پارامترهای صفحه‌بندی
    skip = (page - 1) * page_size
    
    # دریافت کلیدواژه‌ها
    keywords = await keyword_repo.list(skip=skip, limit=page_size)
    total_count = await keyword_repo.count()
    
    # محاسبه تعداد کل صفحات
    total_pages = (total_count + page_size - 1) // page_size
    
    return templates.TemplateResponse(
        "keywords.html",
        {
            "request": request,
            "title": "مدیریت کلیدواژه‌ها",
            "keywords": keywords,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_count": total_count,
                "page_size": page_size
            }
        }
    )


@app.get("/collections", response_class=HTMLResponse)
async def collections_page(
    request: Request, 
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    session: AsyncSession = Depends(get_session)
):
    """صفحه مدیریت جمع‌آوری‌ها"""
    collection_repo = CollectionRepository(session)
    
    # محاسبه پارامترهای صفحه‌بندی
    skip = (page - 1) * page_size
    
    # دریافت جمع‌آوری‌ها
    collections = await collection_repo.list(skip=skip, limit=page_size)
    total_count = await collection_repo.count()
    
    # محاسبه تعداد کل صفحات
    total_pages = (total_count + page_size - 1) // page_size
    
    return templates.TemplateResponse(
        "collections.html",
        {
            "request": request,
            "title": "مدیریت جمع‌آوری‌ها",
            "collections": collections,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_count": total_count,
                "page_size": page_size
            }
        }
    )


@app.get("/tweets", response_class=HTMLResponse)
async def tweets_page(
    request: Request, 
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    keyword: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    """صفحه مشاهده توییت‌ها"""
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
    
    # محاسبه تعداد کل صفحات
    total_pages = (total_count + page_size - 1) // page_size
    
    return templates.TemplateResponse(
        "tweets.html",
        {
            "request": request,
            "title": "مشاهده توییت‌ها",
            "tweets": tweets,
            "keyword": keyword,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_count": total_count,
                "page_size": page_size
            }
        }
    )


@app.post("/api/keywords", response_model=Dict)
async def create_keyword(
    keyword: KeywordCreate,
    session: AsyncSession = Depends(get_session)
):
    """ایجاد کلیدواژه جدید"""
    try:
        repo = KeywordRepository(session)
        result = await repo.get_or_create(text=keyword.text, active=keyword.active)
        
        return {
            "success": True,
            "keyword": {
                "id": str(result.id),
                "text": result.text,
                "active": result.active,
                "created_at": result.created_at.isoformat(),
                "updated_at": result.updated_at.isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error creating keyword: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/collections", response_model=Dict)
async def create_collection(
    collection: CollectionCreate,
    session: AsyncSession = Depends(get_session)
):
    """ایجاد جمع‌آوری جدید"""
    try:
        # ایجاد جمع‌آوری
        collection_repo = CollectionRepository(session)
        keyword_repo = KeywordRepository(session)
        
        # پارامترهای اضافی بر اساس نوع جمع‌آوری
        params = {}
        if collection.collection_type == CollectionType.KEYWORD:
            params["query_type"] = "Latest"
        
        new_collection = await collection_repo.create(
            name=collection.name,
            description=collection.description,
            status=collection.status,
            collection_type=collection.collection_type,
            interval_seconds=collection.interval_seconds,
            parameters=params
        )
        
        # اضافه کردن کلیدواژه‌ها به جمع‌آوری
        for keyword_text in collection.keywords:
            keyword = await keyword_repo.get_or_create(text=keyword_text)
            await collection_repo.add_keyword(new_collection.id, keyword.id)
        
        return {
            "success": True,
            "collection": {
                "id": str(new_collection.id),
                "name": new_collection.name,
                "description": new_collection.description,
                "status": new_collection.status.value,
                "collection_type": new_collection.collection_type.value,
                "interval_seconds": new_collection.interval_seconds,
                "created_at": new_collection.created_at.isoformat(),
                "updated_at": new_collection.updated_at.isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error creating collection: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/collect-now")
async def collect_now(keywords_data: Dict[str, Any]):
    """اجرای فوری جمع‌آوری توییت‌ها بر اساس کلیدواژه‌ها"""
    try:
        # پشتیبانی از هر دو فرمت ورودی
        keyword_list = []
        if isinstance(keywords_data, dict):
            if "keywords" in keywords_data:
                keyword_list = keywords_data.get("keywords", [])
            else:
                # اگر فقط یک کلید دارد و آن کلید یک آرایه است
                values = list(keywords_data.values())
                if len(values) == 1 and isinstance(values[0], list):
                    keyword_list = values[0]
        
        if not keyword_list:
            return {
                "success": False,
                "error": "کلیدواژه‌ای ارائه نشده است"
            }
        
        # ایجاد کلاینت توییتر
        twitter_client = create_twitter_client()
        
        try:
            # اجرای جمع‌آوری
            collected, saved = await collect_by_keywords(
                twitter_client=twitter_client,
                keywords=keyword_list
            )
            
            if collected == 0:
                return {
                    "success": False,
                    "error": "هیچ توییتی یافت نشد"
                }
            
            return {
                "success": True,
                "collected": collected,
                "saved": saved
            }
        except TwitterAPIError as e:
            logger.error(f"Twitter API error: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"خطای API توییتر: {str(e)}"
            }
    except Exception as e:
        logger.error(f"Error collecting tweets: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"خطای جمع‌آوری توییت‌ها: {str(e)}"
        }
    
@app.post("/api/process-tweets", response_model=Dict)
async def process_tweets(
    limit: int = Query(100, ge=1, le=1000)
):
    """پردازش توییت‌ها"""
    try:
        # اجرای پردازش
        processed_count = await TweetProcessingPipeline.process_all_unprocessed(limit=limit)
        
        return {
            "success": True,
            "processed": processed_count
        }
    except Exception as e:
        logger.error(f"Error processing tweets: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """مدیریت سایر خطاها"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "خطای داخلی سرور",
            "details": str(exc) if settings.debug else None
        }
    )

def run_app():
    """اجرای برنامه"""
    import uvicorn
    
    uvicorn.run(
        "src.web.app:app",
        host=settings.web.host,
        port=settings.web.port,
        reload=settings.debug
    )


if __name__ == "__main__":
    run_app()