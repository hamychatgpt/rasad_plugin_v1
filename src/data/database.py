from pathlib import Path
"""
ماژول اتصال به دیتابیس

این ماژول امکانات لازم برای اتصال به دیتابیس و مدیریت جلسه‌ها را فراهم می‌کند.
"""

import contextlib
from typing import Any, AsyncGenerator, Dict, Optional

from sqlalchemy import URL, MetaData, create_engine
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession,
                                    async_sessionmaker, create_async_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings
from src.core.exceptions import DatabaseError

# ایجاد پایه برای مدل‌های SQLAlchemy
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)
Base = declarative_base(metadata=metadata)

# تنظیم موتورهای دیتابیس
async_engine: Optional[AsyncEngine] = None
async_session_factory: Optional[async_sessionmaker] = None


def create_async_db_engine(db_url: str, **kwargs) -> AsyncEngine:
    """ایجاد موتور دیتابیس ناهمگام"""
    try:
        engine_args: Dict[str, Any] = {
            "echo": settings.debug,
            "pool_size": settings.database.pool_size,
            "max_overflow": settings.database.max_overflow,
            "pool_timeout": settings.database.pool_timeout,
            "pool_recycle": settings.database.pool_recycle,
            **kwargs
        }
        
        # اگر URL با sqlite شروع شود، تنظیمات خاص sqlite را اعمال می‌کنیم
        if db_url.startswith("sqlite"):
            # برای sqlite، pool_size و max_overflow کاربردی ندارند
            engine_args.pop("pool_size", None)
            engine_args.pop("max_overflow", None)
            engine_args.pop("pool_timeout", None)
            engine_args.pop("pool_recycle", None)
            
            # اگر URL با // شروع نشود، آن را به فرمت استاندارد تبدیل می‌کنیم
            if not db_url.startswith("sqlite://"):
                # استفاده از مسیر نسبی به جای Path.home()
                data_dir = Path(os.environ.get("DATA_DIR", ".")).resolve()
                db_path = data_dir / "rasad.db"
                db_url = f"sqlite+aiosqlite:///{db_path}"
            else:
                db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://")
            
            engine_args["connect_args"] = {"check_same_thread": False}
            logger.info(f"Using SQLite database at {db_url}")
        
        # برای PostgreSQL
        elif db_url.startswith("postgresql"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
            logger.info(f"Using PostgreSQL database")
        
        return create_async_engine(db_url, **engine_args)
    
    except Exception as e:
        logger.error(f"Failed to create async database engine: {e}", exc_info=True)
        raise DatabaseError(f"Failed to create async database engine: {str(e)}")

def setup_db(db_url: Optional[str] = None) -> None:
    """راه‌اندازی اتصال‌های دیتابیس"""
    global async_engine, async_session_factory
    
    url = db_url or settings.database.url
    
    try:
        # ایجاد موتور ناهمگام
        async_engine = create_async_db_engine(url)
        
        # ایجاد کارخانه جلسه‌های ناهمگام
        async_session_factory = async_sessionmaker(
            bind=async_engine,
            expire_on_commit=False,
            autoflush=False
        )
    
    except Exception as e:
        raise DatabaseError(f"Failed to setup database: {str(e)}")


@contextlib.asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """دریافت جلسه دیتابیس با مدیریت متن ناهمگام"""
    if async_session_factory is None:
        setup_db()
    
    assert async_session_factory is not None
    
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise DatabaseError(f"Database session error: {str(e)}")
    finally:
        await session.close()


async def create_tables() -> None:
    """ایجاد تمام جدول‌های تعریف شده در دیتابیس"""
    if async_engine is None:
        setup_db()
    
    assert async_engine is not None
    
    try:
        # ایجاد جدول‌ها
        async with async_engine.begin() as conn:
            # در حالت توسعه با تنظیم محیطی RESET_DB=true، جدول‌ها را از ابتدا ایجاد می‌کنیم
            if settings.debug and os.environ.get("RESET_DB", "").lower() == "true":
                logger.warning("Dropping all database tables due to RESET_DB=true")
                await conn.run_sync(Base.metadata.drop_all)
            
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created or verified")
    
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}", exc_info=True)
        raise DatabaseError(f"Failed to create database tables: {str(e)}")

async def close_db_connections() -> None:
    """بستن تمام اتصال‌های دیتابیس"""
    if async_engine is not None:
        await async_engine.dispose()