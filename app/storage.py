"""
Historical Storage — Persists cost & resource snapshots to MongoDB
for trend analysis, anomaly detection, and period comparisons.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HistoricalStorage:
    """
    Stores snapshots of cost and resource data in MongoDB.
    
    Collections:
      - cost_snapshots:     {user_id, query_type, time_range, breakdown, total_cost, captured_at}
      - resource_snapshots: {user_id, resource_type, resources, region, captured_at}
    """

    def __init__(self, db):
        """
        Args:
            db: Motor database instance or JSONDatabase (from app.local_db)
        """
        self.db = db
        self._ensure_collections()

    def _ensure_collections(self):
        """Ensure snapshot collections exist (for JSONDatabase fallback)."""
        if hasattr(self.db, 'cost_snapshots'):
            return  # Already has the attribute
        # For Motor, collections are created lazily on first write — nothing to do

    # ─── Cost Snapshots ───────────────────────────────────────────────────────

    async def save_cost_snapshot(
        self,
        user_id: str,
        query_type: str,
        time_range: Dict[str, str],
        total_cost: float,
        breakdown: Optional[List[Dict]] = None,
        granularity: Optional[str] = None,
        points: Optional[List[Dict]] = None,
        currency: str = "USD",
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """
        Save a cost query result as a historical snapshot.
        Returns the inserted document ID, or None on failure.
        """
        try:
            doc = {
                "user_id": user_id,
                "query_type": query_type,          # e.g. "COST_BREAKDOWN", "COST_TIME_SERIES"
                "time_range": time_range,           # {"start": "2026-03-01", "end": "2026-03-31"}
                "total_cost": total_cost,
                "currency": currency,
                "breakdown": breakdown,             # [{name, cost, percentage}, ...]
                "granularity": granularity,          # "DAILY", "MONTHLY"
                "points": points,                    # [{date, cost}, ...] for time series
                "metadata": metadata or {},
                "captured_at": datetime.utcnow(),
            }
            result = await self.db.cost_snapshots.insert_one(doc)
            logger.info(f"[Storage] Cost snapshot saved for user={user_id}, type={query_type}, total=${total_cost:.2f}")
            return str(result.inserted_id)
        except Exception as e:
            logger.warning(f"[Storage] Failed to save cost snapshot: {e}")
            return None

    async def get_cost_history(
        self,
        user_id: str,
        months: int = 3,
        query_type: Optional[str] = None,
    ) -> List[Dict]:
        """
        Fetch historical cost snapshots for a user.
        Returns most recent snapshots within the given timeframe.
        """
        try:
            since = datetime.utcnow() - timedelta(days=months * 30)
            query = {"user_id": user_id, "captured_at": {"$gte": since}}
            if query_type:
                query["query_type"] = query_type

            cursor = self.db.cost_snapshots.find(query).sort("captured_at", -1)
            results = await cursor.to_list(length=100)
            return results
        except Exception as e:
            logger.warning(f"[Storage] Failed to fetch cost history: {e}")
            return []

    async def get_previous_snapshot(
        self,
        user_id: str,
        query_type: str,
        current_time_range: Dict[str, str],
    ) -> Optional[Dict]:
        """
        Find a previous snapshot for the same query type but a different period.
        Useful for month-over-month comparisons.
        """
        try:
            query = {
                "user_id": user_id,
                "query_type": query_type,
                "time_range": {"$ne": current_time_range},
            }
            cursor = self.db.cost_snapshots.find(query).sort("captured_at", -1)
            results = await cursor.to_list(length=1)
            return results[0] if results else None
        except Exception as e:
            logger.warning(f"[Storage] Failed to fetch previous snapshot: {e}")
            return None

    # ─── Resource Snapshots ────────────────────────────────────────────────────

    async def save_resource_snapshot(
        self,
        user_id: str,
        resource_type: str,
        resources: List[Dict],
        region: str = "us-east-1",
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """Save a resource listing as a historical snapshot."""
        try:
            doc = {
                "user_id": user_id,
                "resource_type": resource_type,
                "resource_count": len(resources),
                "resources": resources,
                "region": region,
                "metadata": metadata or {},
                "captured_at": datetime.utcnow(),
            }
            result = await self.db.resource_snapshots.insert_one(doc)
            logger.info(f"[Storage] Resource snapshot saved: {resource_type} ({len(resources)} items)")
            return str(result.inserted_id)
        except Exception as e:
            logger.warning(f"[Storage] Failed to save resource snapshot: {e}")
            return None

    async def get_resource_history(
        self,
        user_id: str,
        resource_type: Optional[str] = None,
        months: int = 3,
    ) -> List[Dict]:
        """Fetch historical resource snapshots."""
        try:
            since = datetime.utcnow() - timedelta(days=months * 30)
            query = {"user_id": user_id, "captured_at": {"$gte": since}}
            if resource_type:
                query["resource_type"] = resource_type

            cursor = self.db.resource_snapshots.find(query).sort("captured_at", -1)
            results = await cursor.to_list(length=50)
            return results
        except Exception as e:
            logger.warning(f"[Storage] Failed to fetch resource history: {e}")
            return []

    # ─── Insights Storage ──────────────────────────────────────────────────────

    async def save_insights(
        self,
        user_id: str,
        insights: List[Dict],
        context: Optional[Dict] = None,
    ) -> Optional[str]:
        """Persist generated insights for dashboard retrieval."""
        try:
            doc = {
                "user_id": user_id,
                "insights": insights,
                "context": context or {},
                "generated_at": datetime.utcnow(),
            }
            result = await self.db.insights.insert_one(doc)
            return str(result.inserted_id)
        except Exception as e:
            logger.warning(f"[Storage] Failed to save insights: {e}")
            return None

    async def get_latest_insights(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get the most recent insights for a user."""
        try:
            cursor = self.db.insights.find({"user_id": user_id}).sort("generated_at", -1)
            results = await cursor.to_list(length=limit)
            return results
        except Exception as e:
            logger.warning(f"[Storage] Failed to fetch insights: {e}")
            return []
