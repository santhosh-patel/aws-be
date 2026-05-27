"""
Session Context Manager - Stores conversation state for follow-up queries
Supports modifiers like currency conversion, granularity changes, etc.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import threading


@dataclass
class SessionContext:
    """Store conversation context for a session"""
    session_id: str
    user_id: str
    last_intent: Optional[str] = None
    last_time_range: Optional[Dict[str, str]] = None  # {start_date, end_date}
    last_result: Optional[Dict[str, Any]] = None
    last_currency: str = "USD"
    last_services: List[str] = field(default_factory=list)
    last_response_type: Optional[str] = None  # COST_SUMMARY, COST_TREND, etc.
    last_granularity: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    
    def is_expired(self, ttl_minutes: int = 30) -> bool:
        """Check if context has expired"""
        expiry = self.last_accessed + timedelta(minutes=ttl_minutes)
        return datetime.utcnow() > expiry
    
    def touch(self):
        """Update last accessed time"""
        self.last_accessed = datetime.utcnow()


class ContextManager:
    """Manages session contexts with TTL cleanup"""
    
    def __init__(self, ttl_minutes: int = 30, max_sessions: int = 10000):
        self.contexts: Dict[str, SessionContext] = {}
        self.ttl_minutes = ttl_minutes
        self.max_sessions = max_sessions
        self.lock = threading.Lock()
    
    def get_context(self, session_id: str, user_id: str) -> SessionContext:
        """
        Get or create session context.
        
        Args:
            session_id: Chat/session identifier
            user_id: User identifier
            
        Returns:
            SessionContext instance
        """
        with self.lock:
            # Cleanup expired sessions first
            self._cleanup_expired()
            
            if session_id in self.contexts:
                context = self.contexts[session_id]
                if context.is_expired(self.ttl_minutes):
                    # Expired, create new
                    context = SessionContext(session_id=session_id, user_id=user_id)
                    self.contexts[session_id] = context
                else:
                    context.touch()
                return context
            
            # Create new context
            context = SessionContext(session_id=session_id, user_id=user_id)
            self.contexts[session_id] = context
            return context
    
    def save_context(self, context: SessionContext):
        """
        Save/update session context.
        
        Args:
            context: SessionContext to save
        """
        with self.lock:
            context.touch()
            self.contexts[context.session_id] = context
            
            # Enforce max sessions limit
            if len(self.contexts) > self.max_sessions:
                # Remove oldest expired or least recently used
                to_remove = sorted(
                    self.contexts.items(),
                    key=lambda x: x[1].last_accessed
                )[:len(self.contexts) - self.max_sessions]
                
                for session_id, _ in to_remove:
                    del self.contexts[session_id]
    
    def update_result(
        self,
        session_id: str,
        user_id: str,
        intent: str,
        result: Dict[str, Any],
        response_type: Optional[str] = None,
        time_range: Optional[Dict[str, str]] = None,
        services: Optional[List[str]] = None,
        granularity: Optional[str] = None
    ):
        """
        Update context with latest query result.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            intent: Canonical intent
            result: Execution result data
            response_type: Response type (COST_SUMMARY, etc.)
            time_range: Time range dict
            services: List of services
            granularity: DAILY or MONTHLY
        """
        context = self.get_context(session_id, user_id)
        
        context.last_intent = intent
        context.last_result = result
        context.last_response_type = response_type
        
        if time_range:
            context.last_time_range = time_range
        
        if services:
            context.last_services = services
        
        if granularity:
            context.last_granularity = granularity
        
        # Extract currency from result if available
        if result and isinstance(result, dict):
            response_data = result.get('response', {})
            if 'currency' in response_data:
                context.last_currency = response_data['currency']
        
        self.save_context(context)
    
    def clear_context(self, session_id: str):
        """Clear a specific session context"""
        with self.lock:
            if session_id in self.contexts:
                del self.contexts[session_id]
    
    def _cleanup_expired(self):
        """Remove expired contexts (called with lock held)"""
        expired = [
            sid for sid, ctx in self.contexts.items()
            if ctx.is_expired(self.ttl_minutes)
        ]
        
        for session_id in expired:
            del self.contexts[session_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about context manager"""
        with self.lock:
            return {
                "active_sessions": len(self.contexts),
                "max_sessions": self.max_sessions,
                "ttl_minutes": self.ttl_minutes
            }


# Global instance
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get global context manager instance"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
