import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from functools import lru_cache
from .local_db import JSONDatabase

# We need a global variable to hold the chosen DB implementation
# because lru_cache might cache the *client* but not the *database instance* decision logic effectively if connection fails later.
_db_instance = None

async def init_db():
    global _db_instance
    mongodb_url = os.getenv("MONGODB_URL")
    env = (os.getenv("ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()
    is_production = env in ("production", "prod")
    
    if is_production and not mongodb_url:
        raise RuntimeError("MONGODB_URL is required in production. Set ENV=production only when MongoDB is configured.")
    
    if mongodb_url:
        try:
            client = AsyncIOMotorClient(
                mongodb_url, 
                serverSelectionTimeoutMS=2000,
                uuidRepresentation='standard'
            )
            await client.admin.command('ping')
            print("[OK] Connected to MongoDB Atlas")
            _db_instance = client.get_database("aws_mcp_agent")
            return
        except Exception as e:
            if is_production:
                raise RuntimeError(f"MongoDB connection failed in production: {e}") from e
            print(f"WARN: MongoDB connection failed: {e}")
    
    print("WARN: Falling back to Local JSON Database (backend/data/)")
    data_dir = os.getenv("TEST_DATA_DIR") or os.path.join(os.getcwd(), "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    _db_instance = JSONDatabase(data_dir)

def get_database():
    return _db_instance
