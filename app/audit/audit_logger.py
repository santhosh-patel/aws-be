from datetime import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel
from ..planner.models import CanonicalIntent, PlanStep, ExecutionPlan
from ..db import get_database

class AuditLog(BaseModel):
    request_id: str
    timestamp: datetime
    user_id: str
    user_role: Optional[str] = "VIEWER"
    raw_query: str
    canonical_intent: Optional[CanonicalIntent] = None
    plan: Optional[ExecutionPlan] = None
    execution_result: Optional[Dict[str, Any]] = None
    duration_ms: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}

from fastapi.encoders import jsonable_encoder

class AuditLogger:
    """
    Logs every request, preventing date encoding errors
    """
    def __init__(self):
        self.collection_name = "audit_logs"

    async def log_event(self, log_entry: AuditLog):
        try:
            db = get_database()
            if db is None:
                print(f"[AUDIT-FALLBACK] {log_entry.json()}")
                return

            # Use jsonable_encoder to handle datetime.date and other types
            document = jsonable_encoder(log_entry)
            
            if hasattr(db, "audit_logs"):
                 await db.audit_logs.insert_one(document)
            else:
                 collection = getattr(db, self.collection_name)
                 await collection.insert_one(document)
                 
        except Exception as e:
            print(f"WARN: Audit Logging Failed: {e}")
            # Do NOT raise, audit failure should not break application flow unless strict compliance mode
