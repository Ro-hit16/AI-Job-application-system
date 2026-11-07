import asyncio
from app.database import engine

async def test():
    try:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql("SELECT 1")
            print("SQLAlchemy connection successful:", result.scalar())
    except Exception as e:
        print("Database error:", repr(e))
    finally:
        await engine.dispose()

asyncio.run(test())