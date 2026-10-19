import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

# 加载 .env；覆盖进程里残留的空/测试密钥，避免抽取走无效 api key
load_dotenv(override=True)

# 获取数据库连接地址
DATABASE_URL = os.getenv("DATABASE_URL")

# 创建异步引擎
engine = create_async_engine(DATABASE_URL, echo=True)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

# 创建基础映射类，所有的表模型都会继承它
Base = declarative_base()