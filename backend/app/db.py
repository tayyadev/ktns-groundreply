from collections.abc import AsyncGenerator

from sqlalchemy import event
from pgvector.asyncpg import register_vector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    get_settings().database_url, pool_pre_ping=True, pool_size=10, max_overflow=10
)


@event.listens_for(engine.sync_engine, "connect")
def register_pgvector(dbapi_connection, _connection_record):
    # Asyncpg does not recognize the custom vector OID until its codec is registered.
    # Applied to every pooled connection after the pgvector extension is installed.
    dbapi_connection.run_async(register_vector)


SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as session:
        yield session
