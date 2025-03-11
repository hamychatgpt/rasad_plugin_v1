from setuptools import setup, find_packages

setup(
    name="src",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "fastapi>=0.100.0",
        "uvicorn>=0.22.0",
        "sqlalchemy>=2.0.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",  # افزوده شده
        "aiohttp>=3.8.5",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
        "alembic>=1.11.1",
        "httpx>=0.24.1",
        "asyncio>=3.4.3",
        "anthropic>=0.5.0",
        "apscheduler>=3.10.1",
        "jinja2>=3.1.2",
        "pandas>=2.0.3",
        "pytest>=7.4.0",
        "pytest-asyncio>=0.21.1",
        "aiosqlite>=0.19.0",
        "asyncpg>=0.28.0",
        "itsdangerous>=2.1.2",  # افزوده شده
    ],
)