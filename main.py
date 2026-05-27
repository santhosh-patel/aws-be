import os
import logging
import tempfile
from fastapi import FastAPI, HTTPException, APIRouter, Header, UploadFile, File, WebSocket, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Optional
from app.auth import (
    LoginRequest, LoginResponse, ProfileUpdate, PasswordChange, SettingsUpdate,
    hash_password, generate_token, get_user_by_token, seed_users, store_token, delete_token,
    verify_password, _active_tokens, _token_ttl_days
)

from app.db import get_database, init_db

# Auth dependency: require valid Bearer token and return current user
async def get_current_user(authorization: str = Header(default="", alias="Authorization")):
    db = get_database()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    token = (authorization.replace("Bearer ", "") if authorization and authorization.startswith("Bearer ") else "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")
    user = await get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user

from app.mcp.registry import MCPRegistry
from app.planner import IntentPlanner
from app.executor import ToolExecutor
from app.llm.openai_client import OpenAIClient
# from app.llm.gemini_client import GeminiClient # Deprecated
# Claude client imported conditionally below based on LLM_PROVIDER
from app.llm.response_generator import ResponseGenerator
from app.schemas.chat import ChatCreate, ChatResponseModel, MessageResponseModel
from app.audit.audit_logger import AuditLogger, AuditLog
from app.security.rbac import RoleBasedAccessControl
from app.planner.models import CanonicalIntent, ExecutionPlan
from app.session import get_context_manager
from app.planner.modifier_detector import ModifierDetector, ModifierType
from app.utils import get_currency_converter
from bson import ObjectId
from datetime import datetime, date, timedelta
from typing import List

# Load environment variables
load_dotenv()

logger = logging.getLogger("aws_mcp")

def _cors_origins():
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://enculture-mcp.vercel.app",
        "https://aws-fe-one.vercel.app",
        "https://encultureawsagent.vercel.app",
    ]

def _validate_env():
    """Fail fast in production if required env is missing."""
    env = (os.getenv("ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()
    if env not in ("production", "prod"):
        return
    if not os.getenv("MONGODB_URL"):
        raise RuntimeError("MONGODB_URL is required in production. Set ENV=production only when MongoDB is configured.")

# Initialize FastAPI
app = FastAPI(title="Enculture AWS MCP Agent")

@app.on_event("startup")
async def startup_db_client():
    global historical_storage
    _validate_env()
    await init_db()
    # Seed default users
    db = get_database()
    if db is not None:
        await seed_users(db)
        # Initialize historical storage
        from app.storage import HistoricalStorage
        historical_storage = HistoricalStorage(db)
        logger.info("[OK] Historical Storage initialized")

# CORS configuration (origins from CORS_ORIGINS env, comma-separated)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (slowapi)
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    _rate_limiter = limiter
except Exception:
    _rate_limiter = None
    limiter = None

def _limit(spec):
    """Apply rate limit when slowapi is available."""
    if limiter is not None:
        return limiter.limit(spec)
    return lambda f: f

# Initialize components
registry = None
llm_client = None
planner = None
executor = None
response_generator = None
audit_logger = None
rbac = None
context_manager = None
modifier_detector = None
claude_tools_adapter = None

# LLM Provider configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower().strip()

try:
    # AWS Credentials
    AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    
    # We only initialize if all required env vars are present
    if all([AWS_ACCESS_KEY, AWS_SECRET_KEY]):
        registry = MCPRegistry(AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION)
        logger.info("MCP Registry initialized with %d tools", len(registry.list_tools()))
        
        # ─── LLM Provider Selection ──────────────────────────────────────────
        if LLM_PROVIDER == "sarvam":
            SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
            SARVAM_MODEL = os.getenv("SARVAM_MODEL", "sarvam-30b")
            if SARVAM_API_KEY:
                from app.llm.sarvam_client import SarvamClient
                llm_client = SarvamClient(SARVAM_API_KEY, model=SARVAM_MODEL)
                logger.info("[OK] Initialized Sarvam AI Client (model: %s)", SARVAM_MODEL)
            else:
                logger.warning("SARVAM_API_KEY missing. Trying OpenAI fallback...")
                OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
                if OPENAI_API_KEY:
                    llm_client = OpenAIClient(OPENAI_API_KEY)
                    logger.info("[OK] Initialized OpenAI Client (fallback)")
                else:
                    logger.warning("No LLM API key found. LLM features disabled.")
                
        elif LLM_PROVIDER == "anthropic":
            ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
            ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
            if ANTHROPIC_API_KEY:
                from app.llm.claude_client import AnthropicClient
                llm_client = AnthropicClient(ANTHROPIC_API_KEY, model=ANTHROPIC_MODEL)
                logger.info("[OK] Initialized Anthropic Claude client (model: %s)", ANTHROPIC_MODEL)
                
                # Initialize Claude Tools Adapter for native tool-use
                from app.llm.claude_tools_adapter import ClaudeToolsAdapter
                claude_tools_adapter = ClaudeToolsAdapter(registry)
                logger.info("[OK] Claude Tools Adapter initialized")
            else:
                logger.warning("ANTHROPIC_API_KEY missing. Trying OpenAI fallback...")
                OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
                if OPENAI_API_KEY:
                    llm_client = OpenAIClient(OPENAI_API_KEY)
                    logger.info("[OK] Initialized OpenAI Client (fallback)")
        
        elif LLM_PROVIDER == "openai":
            OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
            if OPENAI_API_KEY:
                llm_client = OpenAIClient(OPENAI_API_KEY)
                logger.info("[OK] Initialized OpenAI Client")
            else:
                logger.warning("OPENAI_API_KEY missing. LLM features disabled.")
        
        else:
            logger.error("Unknown LLM_PROVIDER: '%s'. Supported: sarvam, anthropic, openai", LLM_PROVIDER)
        
        # ─── Initialize Pipeline Components ──────────────────────────────────
        if llm_client:
            planner = IntentPlanner(llm_client, registry)
            executor = ToolExecutor(registry)
            response_generator = ResponseGenerator(llm_client)
            audit_logger = AuditLogger()
            rbac = RoleBasedAccessControl()
            
            # Initialize Context Manager and Modifier Detector
            context_manager = get_context_manager()
            modifier_detector = ModifierDetector()
            
            logger.info("All pipeline components initialized (provider: %s)", LLM_PROVIDER)
        else:
            logger.warning("No LLM client available. Pipeline components not initialized.")
    else:
        logger.warning("AWS credentials missing. Components not initialized.")
    
except Exception as e:
    logger.exception("Initialization error: %s", e)

# Create a router for all API endpoints with /api prefix
# This matches the vercel.json rewrite: /api/(.*) -> app.py
api_router = APIRouter(prefix="/api")

# Request/Response models
class ChatRequest(BaseModel):
    chat_id: Optional[str] = None
    message: str
    mode: Optional[str] = "inventory_aware"
    response_mode: Optional[str] = "friendly"

class ChatResponse(BaseModel):
    response: dict
    plan: Optional[dict] = None
    execution_results: Optional[dict] = None
    response_mode: Optional[str] = "friendly"

@app.get("/")
@app.head("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "aws-mcp-backend",
        "llm_provider": LLM_PROVIDER,
        "llm_ready": llm_client is not None,
        "mcp_tools": len(registry.list_tools()) if registry else 0,
    }

@app.get("/health/ready")
async def health_ready():
    """Readiness: checks MongoDB (or DB) is reachable."""
    db = get_database()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        if hasattr(db, "client"):
            await db.client.admin.command("ping")
    except Exception as e:
        logger.warning("Readiness check failed: %s", e)
        raise HTTPException(status_code=503, detail="Database not ready")
    return {"status": "ready", "service": "aws-mcp-backend"}

@app.get("/health/llm")
def health_llm():
    """LLM provider health check."""
    return {
        "provider": LLM_PROVIDER,
        "ready": llm_client is not None,
        "tools_adapter": claude_tools_adapter is not None,
        "planner": planner is not None,
        "response_generator": response_generator is not None,
    }

@api_router.get("/tools")
async def list_tools(mode: str = "inventory_aware"):
    """List all registered MCP tools."""
    if not registry:
        raise HTTPException(status_code=500, detail="Registry not initialized")
    return {
        "tools": registry.get_tools_catalog(mode),
        "ui_tools": registry.get_ui_tools_catalog(mode),
        "count": len(registry.get_tools_catalog(mode))
    }

from collections import OrderedDict
from typing import Any, Dict

# ─── Data Layer & Analytics ──────────────────────────────────────────────────
from app.cache import ResponseCache
from app.storage import HistoricalStorage
from app.analytics import InsightsEngine

# Initialize Cache (TTL-based, replaces old SimpleCache)
response_cache = ResponseCache(maxsize=256, default_ttl=300)

# Storage & Insights (initialized after DB is ready)
historical_storage = None
insights_engine = InsightsEngine(max_insights=5)

# Legacy SimpleCache wrapper for backward compat
class _CacheCompat:
    """Wraps ResponseCache to match old .get(key) / .put(key, val) API."""
    def __init__(self, cache: ResponseCache):
        self._c = cache
    def get(self, key: str):
        return self._c.get(key, {})
    def put(self, key: str, value):
        self._c.set(key, {}, value)

_cache_compat = _CacheCompat(response_cache)

@api_router.post("/chats", response_model=ChatResponseModel)
async def create_new_chat(chat: ChatCreate, user: dict = Depends(get_current_user)):
    db = get_database()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    user_id = str(user["_id"])
    try:
        new_chat = {
            "title": chat.title or "New Chat",
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await db.chats.insert_one(new_chat)
        created_chat = await db.chats.find_one({"_id": result.inserted_id})
        if created_chat:
            created_chat['_id'] = str(created_chat['_id'])
        return created_chat
    except Exception as e:
        print(f"WARN: Database error in create_new_chat: {str(e)}")
        raise HTTPException(status_code=503, detail="Database error: Failed to create chat")

@api_router.get("/chats", response_model=List[ChatResponseModel])
async def list_chats(user: dict = Depends(get_current_user)):
    db = get_database()
    if db is None:
        return []
    user_id = str(user["_id"])
    try:
        chats = await db.chats.find({"user_id": user_id}).sort("updated_at", -1).to_list(100)
        for chat in chats:
            if '_id' in chat:
                chat['_id'] = str(chat['_id'])
        return chats
    except Exception as e:
        print(f"WARN: Database error in list_chats: {str(e)}")
        return []

@api_router.put("/chats/{chat_id}", response_model=ChatResponseModel)
async def update_chat(chat_id: str, chat_update: ChatCreate, user: dict = Depends(get_current_user)):
    db = get_database()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    user_id = str(user["_id"])
    if not ObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    try:
        result = await db.chats.update_one(
            {"_id": ObjectId(chat_id), "user_id": user_id},
            {"$set": {"title": chat_update.title or "New Chat"}}
        )
        matched = getattr(result, "matched_count", None)
        if matched is None:
            matched = getattr(result, "modified_count", 0)
        if matched == 0:
            existing = await db.chats.find_one({"_id": ObjectId(chat_id)})
            if not existing:
                raise HTTPException(status_code=404, detail="Chat not found")
            raise HTTPException(status_code=404, detail="Chat not found or access denied")
        updated_chat = await db.chats.find_one({"_id": ObjectId(chat_id)})
        if updated_chat:
            updated_chat['_id'] = str(updated_chat['_id'])
        return updated_chat
    except HTTPException:
        raise
    except Exception as e:
        print(f"WARN: Database error in update_chat: {str(e)}")
        raise HTTPException(status_code=503, detail="Database error")

@api_router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, user: dict = Depends(get_current_user)):
    db = get_database()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    user_id = str(user["_id"])
    if not ObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    try:
        await db.messages.delete_many({"chat_id": chat_id})
        result = await db.chats.delete_one({"_id": ObjectId(chat_id), "user_id": user_id})
        if result.deleted_count == 0:
            existing = await db.chats.find_one({"_id": ObjectId(chat_id)})
            if not existing:
                raise HTTPException(status_code=404, detail="Chat not found")
            raise HTTPException(status_code=404, detail="Chat not found or access denied")
        return {"success": True, "message": "Chat deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"WARN: Database error in delete_chat: {str(e)}")
        raise HTTPException(status_code=503, detail="Database error")

@api_router.get("/chats/{chat_id}/messages", response_model=List[MessageResponseModel])
async def get_chat_messages(chat_id: str, user: dict = Depends(get_current_user)):
    db = get_database()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    user_id = str(user["_id"])
    if not ObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    try:
        chat = await db.chats.find_one({"_id": ObjectId(chat_id), "user_id": user_id})
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found or access denied")
        messages = await db.messages.find({"chat_id": chat_id}).sort("timestamp", 1).to_list(1000)
        for message in messages:
            if '_id' in message:
                message['_id'] = str(message['_id'])
        return messages
    except HTTPException:
        raise
    except Exception as e:
        print(f"WARN: Database error in get_chat_messages: {str(e)}")
        return []

@api_router.post("/chat", response_model=ChatResponse)
@_limit("30/minute")
async def chat(chat_request: ChatRequest, request: Request, user: dict = Depends(get_current_user)):
    """
    Main chat endpoint
    """
    if not all([planner, registry, executor, response_generator, audit_logger, rbac]):
         raise HTTPException(status_code=500, detail="Backend components not initialized. Check environment variables.")
    
    db = get_database()
    user_id = str(user["_id"])
    user_role = user.get("role", "USER")

    try:
        user_query = chat_request.message
        mode = chat_request.mode or "inventory_aware"
        response_mode = chat_request.response_mode or "friendly"
        chat_id = chat_request.chat_id
        start_time = datetime.utcnow()
        plan = None
        execution_results = None
        result_payload = None
        
        # Persist User Message (only if chat belongs to current user)
        if chat_id and db is not None:
            if not ObjectId.is_valid(chat_id):
                 raise HTTPException(status_code=400, detail="Invalid chat_id format")
            existing_chat = await db.chats.find_one({"_id": ObjectId(chat_id), "user_id": user_id})
            if not existing_chat:
                raise HTTPException(status_code=404, detail="Chat not found or access denied")
            try:
                await db.messages.insert_one({
                    "chat_id": chat_id,
                    "role": "user",
                    "content": user_query,
                    "timestamp": datetime.utcnow()
                })
                await db.chats.update_one(
                    {"_id": ObjectId(chat_id), "user_id": user_id},
                    {"$set": {"updated_at": datetime.utcnow()}}
                )
            except Exception as e:
                print(f"WARN: Failed to persist user message: {str(e)}")

        # Load session context
        session_context = None
        has_context = False
        session_context_dict = None
        if context_manager and chat_id:
            session_context = context_manager.get_context(chat_id, user_id)
            has_context = session_context.last_result is not None
            session_context_dict = {
                "last_intent": session_context.last_intent,
                "last_time_range": session_context.last_time_range,
                "last_services": getattr(session_context, "last_services", []) or [],
                "last_response_type": getattr(session_context, "last_response_type", None),
            }
        
        # Load conversation history once (for modifiers and normal flow)
        conversation_history = []
        if chat_id and db is not None:
            try:
                history_cursor = db.messages.find(
                    {"chat_id": chat_id},
                    {"role": 1, "content": 1, "_id": 0}
                ).sort("timestamp", -1).limit(10)
                history_msgs = await history_cursor.to_list(length=10)
                history_msgs.reverse()
                for msg in history_msgs:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if isinstance(content, dict):
                        resp = content.get("response", content)
                        content = resp.get("message", resp.get("content", str(resp.get("type", ""))))
                    conversation_history.append({"role": role, "content": str(content)[:500]})
            except Exception as hist_err:
                print(f"WARN: Failed to load conversation history: {hist_err}")
        
        # One-line summary of last agent response for LLM context
        last_agent_summary = None
        for msg in reversed(conversation_history):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, dict):
                    content = content.get("message") or content.get("content") or content.get("ai_message") or str(content.get("type", ""))
                last_agent_summary = (str(content)[:200].strip() if content else None)
                break
        
        # Check for modifier intent (follow-up query)
        modifier_intent = None
        if modifier_detector:
            modifier_intent = modifier_detector.detect(user_query, has_context=has_context)
        
        # Handle modifier intents without re-executing tools
        if modifier_intent:
            if modifier_intent.modifier_type == ModifierType.CURRENCY_CONVERSION:
                # Currency conversion: apply to last result
                target_currency = modifier_intent.params.get('target_currency')
                
                if target_currency == 'UNKNOWN':
                    # Ask user which currency
                    result_payload = {
                        "response": {
                            "type": "CLARIFICATION_NEEDED",
                            "message": "Which currency would you like to convert to? (e.g., INR, EUR, GBP)",
                            "missing_parameters": ["currency"],
                            "suggestions": ["INR", "EUR", "GBP", "JPY"]
                        },
                        "plan": None,
                        "execution_results": None
                    }
                    plan = result_payload.get("plan")
                    execution_results = result_payload.get("execution_results")
                elif not session_context.last_result:
                    # No previous result
                    result_payload = {
                        "response": {
                            "type": "ERROR_STATE",
                            "error_code": "NO_CONTEXT",
                            "message": "No previous cost data found to convert. Please request cost data first.",
                            "suggestion": "Try queries like 'show last month cost' or 'cost for January'",
                            "suggestions": ["Show last month cost", "Cost breakdown by service"],
                        },
                        "plan": None,
                        "execution_results": None
                    }
                    plan = result_payload.get("plan")
                    execution_results = result_payload.get("execution_results")
                else:
                    # Convert last result
                    converter = get_currency_converter()
                    last_response = session_context.last_result.get('response', {})
                    original_amount = last_response.get('total_cost', 0.0)
                    original_currency = last_response.get('currency', 'USD')
                    
                    converted_amount, rate_info = converter.convert(
                        original_amount,
                        from_currency=original_currency,
                        to_currency=target_currency
                    )
                    
                    # Create converted response
                    converted_response = last_response.copy()
                    converted_response['currency_original'] = original_currency
                    converted_response['currency_display'] = target_currency
                    converted_response['total_cost_converted'] = converted_amount
                    converted_response['exchange_rate'] = rate_info.rate
                    converted_response['exchange_rate_source'] = rate_info.source
                    converted_response['conversion_note'] = converter.format_conversion(
                        original_amount, converted_amount, rate_info
                    )
                    
                    result_payload = {
                        "response": converted_response,
                        "plan": session_context.last_result.get('plan'),
                        "execution_results": session_context.last_result.get('execution_results')
                    }
                    # Add context_used so UI can show "Using previous period"
                    tr = session_context.last_time_range or {}
                    start_d = tr.get('start_date', '')
                    end_d = tr.get('end_date', '')
                    if start_d and end_d:
                        converted_response["context_used"] = {
                            "message": f"Using previous period: {start_d} to {end_d}",
                            "time_range": tr,
                        }
                    plan = result_payload.get("plan")
                    execution_results = result_payload.get("execution_results")
                    # Update cached currency in context
                    session_context.last_currency = target_currency
                    context_manager.save_context(session_context)
            
            elif modifier_intent.modifier_type == ModifierType.GRANULARITY_CHANGE:
                # Granularity change: reuse context and re-execute
                target_granularity = modifier_intent.params.get('granularity')
                
                if not session_context.last_intent or not session_context.last_time_range:
                    # No previous query
                    result_payload = {
                        "response": {
                            "type": "ERROR_STATE",
                            "error_code": "NO_CONTEXT",
                            "message": "No previous cost data found. Please request cost data first.",
                            "suggestion": "Try queries like 'show last 4 months cost'",
                            "suggestions": ["Show last month cost", "Show last 3 months cost"],
                        },
                        "plan": None,
                        "execution_results": None
                    }
                    plan = result_payload.get("plan")
                    execution_results = result_payload.get("execution_results")
                else:
                    # Re-plan with new granularity
                    # Build enriched query from context
                    time_range = session_context.last_time_range
                    enriched_query = f"Show cost from {time_range['start_date']} to {time_range['end_date']} in {target_granularity.lower()} view"
                    
                    # Re-execute with explicit granularity
                    plan = await planner.plan(enriched_query, mode=mode)
                    
                    # Override granularity in plan
                    if plan and 'steps' in plan:
                        for step in plan['steps']:
                            if 'parameters' in step:
                                step['parameters']['granularity'] = target_granularity
                    
                    # Execute and generate response
                    execution_results = executor.execute_plan(plan)
                    response_data = response_generator.generate(
                        plan, execution_results,
                        conversation_history=conversation_history,
                        mode=mode, registry=registry,
                        last_agent_summary=last_agent_summary,
                    )
                    
                    result_payload = {
                        "response": response_data,
                        "plan": plan,
                        "execution_results": execution_results
                    }
                    # Add context_used for modifier (granularity change)
                    time_range = session_context.last_time_range or {}
                    start_d = time_range.get('start_date', '')
                    end_d = time_range.get('end_date', '')
                    if start_d and end_d and isinstance(response_data, dict):
                        response_data["context_used"] = {
                            "message": f"Using previous period: {start_d} to {end_d}",
                            "time_range": time_range,
                        }
                    
                    # Update context with new granularity
                    if context_manager and chat_id:
                        context_manager.update_result(
                            session_id=chat_id,
                            user_id=user_id,
                            intent=session_context.last_intent,
                            result=result_payload,
                            response_type=response_data.get('type'),
                            time_range=time_range,
                            services=session_context.last_services,
                            granularity=target_granularity
                        )
            
            elif modifier_intent.modifier_type == ModifierType.FOLLOW_UP_EXPLAIN:
                # Follow-up explanation: "why is this cost more?", "explain this", etc.
                if not session_context or not session_context.last_result:
                    result_payload = {
                        "response": {
                            "type": "ERROR_STATE",
                            "error_code": "NO_CONTEXT",
                            "message": "I don't have previous data to explain. Ask something like 'last month bill' first, then ask your follow-up.",
                            "suggestion": "Try: 'What was my cost last month?' then ask 'Why is this cost more?'",
                            "suggestions": ["What was my cost last month?", "Show cost breakdown by service"],
                        },
                        "plan": None,
                        "execution_results": None
                    }
                    plan = result_payload.get("plan")
                    execution_results = result_payload.get("execution_results")
                else:
                    explanation = response_generator.generate_follow_up_explanation(
                        session_context.last_result,
                        user_query,
                        conversation_history
                    )
                    result_payload = {
                        "response": explanation,
                        "plan": session_context.last_result.get("plan"),
                        "execution_results": session_context.last_result.get("execution_results")
                    }
                    plan = result_payload.get("plan")
                    execution_results = result_payload.get("execution_results")
            
            elif modifier_intent.modifier_type == ModifierType.COMPARISON:
                if not session_context or not session_context.last_time_range or not session_context.last_intent:
                    result_payload = {
                        "response": {
                            "type": "ERROR_STATE",
                            "error_code": "NO_CONTEXT",
                            "message": "No previous cost data found to compare. Please request cost data first.",
                            "suggestion": "Try queries like 'show last month cost' then say 'compare with last month'",
                            "suggestions": ["Show last month cost", "Show last 3 months cost"],
                        },
                        "plan": None,
                        "execution_results": None
                    }
                    plan = result_payload.get("plan")
                    execution_results = result_payload.get("execution_results")
                else:
                    # ── Deterministic comparison: bypass LLM planner entirely ──
                    from datetime import timedelta as td
                    time_range = session_context.last_time_range
                    start_d = time_range.get("start_date", "")
                    end_d = time_range.get("end_date", "")
                    
                    try:
                        cur_start = datetime.strptime(start_d, "%Y-%m-%d")
                        cur_end = datetime.strptime(end_d, "%Y-%m-%d")
                    except (ValueError, TypeError):
                        cur_start = datetime.now().replace(day=1)
                        cur_end = datetime.now()
                    
                    duration = cur_end - cur_start
                    prev_end = cur_start - td(days=1)
                    prev_start = prev_end - duration
                    
                    cur_gran = "DAILY" if duration.days <= 45 else "MONTHLY"
                    prev_gran = "DAILY" if duration.days <= 45 else "MONTHLY"
                    
                    # Build a synthetic plan directly (no LLM round-trip)
                    plan = {
                        "intent": {
                            "intent": "COST_COMPARE",
                            "comparison": "time",
                            "time_range": {
                                "start_date": start_d,
                                "end_date": end_d,
                            },
                            "confidence": 1.0,
                        },
                        "steps": [
                            {
                                "tool_name": "aws_get_cost_by_time_range",
                                "arguments": {
                                    "start_date": start_d,
                                    "end_date": end_d,
                                    "granularity": cur_gran,
                                },
                                "description": f"Get cost for current period ({start_d} to {end_d})",
                            },
                            {
                                "tool_name": "aws_get_cost_by_time_range",
                                "arguments": {
                                    "start_date": prev_start.strftime("%Y-%m-%d"),
                                    "end_date": prev_end.strftime("%Y-%m-%d"),
                                    "granularity": prev_gran,
                                },
                                "description": f"Get cost for previous period ({prev_start.strftime('%Y-%m-%d')} to {prev_end.strftime('%Y-%m-%d')})",
                            },
                        ],
                        "user_query": user_query,
                        "explanation": f"Comparing cost: {start_d}–{end_d} vs {prev_start.strftime('%Y-%m-%d')}–{prev_end.strftime('%Y-%m-%d')}",
                    }
                    
                    execution_results = executor.execute_plan(plan)
                    response_data = response_generator.generate(
                        plan, execution_results,
                        conversation_history=conversation_history,
                        mode=mode, registry=registry,
                        last_agent_summary=last_agent_summary,
                    )
                    result_payload = {"response": response_data, "plan": plan, "execution_results": execution_results}
                    if isinstance(response_data, dict):
                        response_data["context_used"] = {
                            "message": f"Comparing with previous period (same length as {start_d} to {end_d})",
                            "time_range": time_range,
                        }
                    if context_manager and chat_id:
                        context_manager.update_result(
                            session_id=chat_id,
                            user_id=user_id,
                            intent=session_context.last_intent,
                            result=result_payload,
                            response_type=response_data.get("type"),
                            time_range=time_range,
                        )
                    plan = result_payload.get("plan")
                    execution_results = result_payload.get("execution_results")
            
            elif modifier_intent.modifier_type == ModifierType.SERVICE_FILTER:
                action = modifier_intent.params.get("action", "include")
                service_hint = modifier_intent.params.get("service_hint", "").strip()
                if not service_hint:
                    result_payload = {
                        "response": {
                            "type": "CLARIFICATION_NEEDED",
                            "message": "Which service do you mean? (e.g. EC2, S3, Lambda)",
                            "suggestions": ["Cost for EC2", "Cost for S3", "List Lambda functions"],
                        },
                        "plan": None,
                        "execution_results": None
                    }
                    plan = result_payload.get("plan")
                    execution_results = result_payload.get("execution_results")
                elif session_context and session_context.last_time_range and session_context.last_intent and "COST" in (session_context.last_intent or ""):
                    start_d = session_context.last_time_range.get("start_date", "")
                    end_d = session_context.last_time_range.get("end_date", "")
                    enriched_query = f"Cost for {service_hint} from {start_d} to {end_d}"
                    plan = await planner.plan(enriched_query, mode=mode, conversation_history=conversation_history, session_context=session_context_dict)
                    execution_results = executor.execute_plan(plan)
                    response_data = response_generator.generate(plan, execution_results, conversation_history=conversation_history, mode=mode, registry=registry, last_agent_summary=last_agent_summary)
                    result_payload = {"response": response_data, "plan": plan, "execution_results": execution_results}
                    if isinstance(response_data, dict):
                        response_data["context_used"] = {"message": f"Using previous period: {start_d} to {end_d}", "time_range": session_context.last_time_range}
                    if context_manager and chat_id:
                        context_manager.update_result(session_id=chat_id, user_id=user_id, intent=plan.get("intent", {}).get("intent") if plan else None, result=result_payload, response_type=response_data.get("type"), time_range=session_context.last_time_range)
                    plan = result_payload.get("plan")
                    execution_results = result_payload.get("execution_results")
                else:
                    enriched_query = f"List {service_hint} resources"
                    plan = await planner.plan(enriched_query, mode=mode, conversation_history=conversation_history, session_context=session_context_dict)
                    execution_results = executor.execute_plan(plan)
                    response_data = response_generator.generate(plan, execution_results, conversation_history=conversation_history, mode=mode, registry=registry, last_agent_summary=last_agent_summary)
                    result_payload = {"response": response_data, "plan": plan, "execution_results": execution_results}
                    if context_manager and chat_id:
                        context_manager.update_result(session_id=chat_id, user_id=user_id, intent=plan.get("intent", {}).get("intent") if plan else None, result=result_payload, response_type=response_data.get("type"))
                    plan = result_payload.get("plan")
                    execution_results = result_payload.get("execution_results")
            
            else:
                # Other modifiers (granularity, service filter, etc.) - re-plan with context
                # For now, fall through to normal planning
                modifier_intent = None
        
        # Normal flow if not a modifier
        if not modifier_intent:
            # Simple cache key initially (before plan is created)
            simple_cache_key = f"{user_id}:{mode}:{user_query}"
            cached_response = _cache_compat.get(simple_cache_key)
        else:
            # Modifier detected, skip cache
            cached_response = None
        
        # Only use cache for simple queries without tool usage
        if cached_response and "[Use Tool:" not in user_query and response_mode == "friendly": 
             result_payload = cached_response
             plan = result_payload.get("plan")
             execution_results = result_payload.get("execution_results")
        elif not modifier_intent:
            # Run plan/execute only when no modifier was handled (modifier path already set result_payload)
            # conversation_history already loaded above
            plan = await planner.plan(user_query, mode=mode, conversation_history=conversation_history, session_context=session_context_dict)
            
            # Enhanced cache key with intent (after plan is created)
            intent_str = str(plan.get('intent', {}).get('intent', 'UNKNOWN')) if plan else 'UNKNOWN'
            cache_key = f"{user_id}:{mode}:{intent_str}:{user_query}"
            
            # Check if this intent is cacheable
            cacheable_intents = ['COST_TOTAL', 'GREETING', 'CONVERSATIONAL', 'ACCOUNT_METADATA']
            is_cacheable = (
                intent_str in cacheable_intents and 
                "[Use Tool:" not in user_query and 
                response_mode == "friendly"
            )
            if not plan:
                raise ValueError("Planner returned None")
            
            # RBAC Enforcement
            if rbac:
                intent_name = plan.get('intent', {}).get('intent', 'UNKNOWN')
                if not rbac.verify_permission(user_role, intent_name):
                    # Audit Log the denial (optional, but good practice)
                    raise HTTPException(status_code=403, detail=f"Permission denied: Roles {user_role} cannot execute {intent_name}")
            
            execution_results = executor.execute_plan(plan)
            if not execution_results:
                execution_results = {"success": False, "error": "Executor returned None"}
            
            if response_mode == 'raw':
                import json
                response_data = {
                    "type": "LLM_RESPONSE",
                    "content": f"```json\n{json.dumps(execution_results, indent=2)}\n```",
                    "message": "Raw output from tool execution."
                }
            else:
                response_data = response_generator.generate(
                    plan, execution_results,
                    conversation_history=conversation_history,
                    mode=mode, registry=registry,
                    last_agent_summary=last_agent_summary,
                )
            
            if not isinstance(response_data, dict) or 'type' not in response_data:
                response_data = {
                    "type": "ERROR_STATE",
                    "error_code": "UNKNOWN_ERROR",
                    "message": "Failed to generate valid response",
                    "suggestion": "Please try again"
                }
            
            result_payload = {
                "response": response_data,
                "plan": plan,
                "execution_results": execution_results
            }
            
            # ── Run Insights Engine ──────────────────────────────────────
            if insights_engine and isinstance(response_data, dict) and response_data.get('type') not in ('ERROR_STATE', 'CLARIFICATION_NEEDED', 'CONVERSATIONAL'):
                try:
                    history = []
                    if historical_storage:
                        history = await historical_storage.get_cost_history(user_id, months=3, query_type=response_data.get('type'))
                    generated_insights = insights_engine.analyze(response_data, history=history)
                    if generated_insights:
                        response_data['insights'] = generated_insights
                except Exception as insight_err:
                    logger.warning(f"Insights generation failed: {insight_err}")

            # ── Save Historical Snapshot ─────────────────────────────────
            if historical_storage and isinstance(response_data, dict) and response_data.get('type') not in ('ERROR_STATE', 'CLARIFICATION_NEEDED', 'CONVERSATIONAL'):
                try:
                    resp_type = response_data.get('type', '')
                    if resp_type in ('COST_SUMMARY', 'COST_BREAKDOWN', 'COST_TIME_SERIES'):
                        await historical_storage.save_cost_snapshot(
                            user_id=user_id,
                            query_type=resp_type,
                            time_range=response_data.get('time_range', {}),
                            total_cost=response_data.get('total_cost', 0),
                            breakdown=response_data.get('breakdown'),
                            granularity=response_data.get('granularity'),
                            points=response_data.get('points'),
                        )
                    elif resp_type == 'RESOURCE_LIST':
                        await historical_storage.save_resource_snapshot(
                            user_id=user_id,
                            resource_type=response_data.get('resource_type', ''),
                            resources=response_data.get('resources', []),
                            region=os.getenv('AWS_REGION', 'us-east-1'),
                        )
                except Exception as storage_err:
                    logger.warning(f"Snapshot storage failed: {storage_err}")

            # Store in cache using enhanced key (only if cacheable intent)
            if response_data.get('type') != 'ERROR_STATE' and is_cacheable:
                _cache_compat.put(cache_key, result_payload)
            
            # Save to session context for follow-up queries
            if context_manager and chat_id and response_data.get('type') not in ['ERROR_STATE', 'CLARIFICATION_NEEDED']:
                intent_obj = plan.get('intent', {})
                intent_name = intent_obj.get('intent') if isinstance(intent_obj, dict) else str(intent_obj)
                time_range_obj = intent_obj.get('time_range') if isinstance(intent_obj, dict) else None
                
                # Extract time range as dict
                time_range_dict = None
                if time_range_obj:
                    time_range_dict = {
                        'start_date': time_range_obj.get('start_date') if isinstance(time_range_obj, dict) else getattr(time_range_obj, 'start_date', None),
                        'end_date': time_range_obj.get('end_date') if isinstance(time_range_obj, dict) else getattr(time_range_obj, 'end_date', None)
                    }
                
                context_manager.update_result(
                    session_id=chat_id,
                    user_id=user_id,
                    intent=intent_name,
                    result=result_payload,
                    response_type=response_data.get('type'),
                    time_range=time_range_dict,
                    services=intent_obj.get('services', []) if isinstance(intent_obj, dict) else [],
                    granularity=response_data.get('granularity')
                )
        
        # Audit Logging
        if audit_logger:
            try:
                duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                log_entry = AuditLog(
                    request_id=str(ObjectId()), 
                    timestamp=start_time,
                    user_id=user_id,
                    user_role=user_role,
                    raw_query=user_query,
                    canonical_intent=CanonicalIntent(**plan['intent']) if plan and 'intent' in plan else None,
                    plan=ExecutionPlan(**plan) if plan else None,
                    execution_result=execution_results if 'execution_results' in locals() else None,
                    duration_ms=duration,
                    error=result_payload.get('response', {}).get('message') if result_payload.get('response', {}).get('type') == 'ERROR_STATE' else None
                )
                await audit_logger.log_event(log_entry)
            except Exception as audit_err:
                 print(f"WARN: Audit log error: {str(audit_err)}")

        # Persist Assistant Response
        if chat_id and db is not None:
            try:
                def recursive_json_sanitize(obj):
                    if isinstance(obj, dict):
                        return {k: recursive_json_sanitize(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [recursive_json_sanitize(i) for i in obj]
                    elif isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    return obj

                sanitized_payload = recursive_json_sanitize(result_payload)

                await db.messages.insert_one({
                    "chat_id": chat_id,
                    "role": "assistant",
                    "content": sanitized_payload, # Store full payload (response, plan, execution)
                    "timestamp": datetime.utcnow()
                })
                await db.chats.update_one(
                    {"_id": ObjectId(chat_id), "user_id": user_id},
                    {"$set": {"updated_at": datetime.utcnow()}}
                )
            except Exception as e:
                 print(f"WARN: Failed to persist assistant message: {str(e)}")

        return ChatResponse(**result_payload)

    
    except Exception as e:
        import traceback
        logger.error("Chat endpoint error: %s", str(e))
        logger.debug("Traceback: %s", traceback.format_exc())
        # Sanitize error in production — don't expose internal details
        env = (os.getenv("ENV") or "development").strip().lower()
        if env in ("production", "prod"):
            raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/plan")
async def plan_only(request: ChatRequest):
    if not planner:
        raise HTTPException(status_code=500, detail="Planner not initialized")
    try:
        plan = await planner.plan(request.message, mode=request.mode or "inventory_aware")
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# ─── Dashboard Aggregation Endpoint ──────────────────────────────────────────

_dashboard_aggregate_cache: Dict[str, Any] = {"payload": None, "expires_at": 0.0}
DASHBOARD_CACHE_TTL_SEC = 180


@api_router.get("/dashboard")
async def get_dashboard(
    refresh: bool = False,
    user: dict = Depends(get_current_user),
):
    """
    Comprehensive AWS dashboard — cost, resources, utilization, tags, burn rate, insights.
    Cached 3 minutes unless refresh=true.
    """
    if not executor or not registry:
        raise HTTPException(status_code=500, detail="Backend not initialized")

    import time
    from app.dashboard import build_dashboard

    now = time.time()
    if (
        not refresh
        and _dashboard_aggregate_cache["payload"] is not None
        and now < _dashboard_aggregate_cache["expires_at"]
    ):
        return _dashboard_aggregate_cache["payload"]

    payload = build_dashboard(executor, insights_engine)
    _dashboard_aggregate_cache["payload"] = payload
    _dashboard_aggregate_cache["expires_at"] = now + DASHBOARD_CACHE_TTL_SEC
    return payload


@api_router.get("/dashboard/drilldown")
async def get_dashboard_drilldown(
    kind: str,
    service: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Lazy drill-down data (usage types, etc.) to keep initial dashboard payload smaller."""
    if not executor:
        raise HTTPException(status_code=500, detail="Backend not initialized")

    from datetime import datetime, timedelta
    today = datetime.now()
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    tomorrow_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        if kind == "usage_type":
            result = executor.execute_tool("aws_get_cost_by_usage_type", {
                "start_date": month_start,
                "end_date": tomorrow_str,
            })
            if not result.get("success"):
                raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
            data = result.get("data", {})
            if service:
                svc_lower = service.lower()
                data["breakdown"] = [
                    b for b in data.get("breakdown", [])
                    if svc_lower in (b.get("usage_type") or "").lower()
                ][:20]
            return data

        raise HTTPException(status_code=400, detail=f"Unknown drilldown kind: {kind}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Dashboard drilldown error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/dashboard/trend")
async def get_dashboard_trend(months: int = 1, user: dict = Depends(get_current_user)):
    """Fetch cost trend for a specific interval (used for the frontend dropdown)."""
    if not executor:
        raise HTTPException(status_code=500, detail="Backend not initialized")

    from datetime import datetime, timedelta
    today = datetime.now()
    
    # Calculate start date based on months
    start_date = (today - timedelta(days=30 * months)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    
    # For 1 month, use DAILY. For >1 month, use MONTHLY
    granularity = "MONTHLY" if months > 1 else "DAILY"

    try:
        # Run tool
        result = executor.execute_tool("aws_get_cost_trend", {
            "start_date": start_date,
            "end_date": end_date,
            "granularity": granularity
        })
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
            
        return result.get("data", {})
    except Exception as e:
        logger.error(f"Cost trend error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Auth Routes ─────────────────────────────────────────────────────────────

@api_router.post("/auth/login")
@_limit("10/minute")
async def login(req: LoginRequest, request: Request):
    db = get_database()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    user = await db.users.find_one({"email": req.email})
    if not user or not verify_password(req.password, user.get("password_hash") or ""):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Migrate legacy SHA-256 hash to bcrypt on successful login
    stored = user.get("password_hash") or ""
    if not (stored.startswith("$2") or stored.startswith("$2a") or stored.startswith("$2b")):
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"password_hash": hash_password(req.password)}}
        )
    
    token = generate_token()
    ttl_days = _token_ttl_days()
    expires_at = datetime.utcnow() + timedelta(days=ttl_days)
    if hasattr(db, "tokens"):
        await store_token(db, token, str(user["_id"]), expires_at)
    else:
        _active_tokens[token] = str(user["_id"])
    
    user_safe = {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "USER"),
        "avatar_url": user.get("avatar_url", "")
    }
    return {"token": token, "user": user_safe}

@api_router.post("/auth/logout", status_code=204)
async def logout(authorization: str = Header(default="", alias="Authorization")):
    """Invalidate the current token server-side."""
    db = get_database()
    token = (authorization.replace("Bearer ", "") if authorization and authorization.startswith("Bearer ") else "").strip()
    if token and db and hasattr(db, "tokens"):
        await delete_token(db, token)
    elif token and _active_tokens:
        _active_tokens.pop(token, None)
    return None

@api_router.get("/auth/me")
async def get_me(authorization: str = Header(default="", alias="Authorization")):
    token = (authorization.replace("Bearer ", "") if authorization and authorization.startswith("Bearer ") else "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")
    
    db = get_database()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    user = await get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return {
        "id": user["_id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "USER"),
        "avatar_url": user.get("avatar_url", "")
    }

@api_router.get("/users/profile")
async def get_profile(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    db = get_database()
    user = await get_user_by_token(db, token) if db is not None else None
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "id": user["_id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "USER"),
        "avatar_url": user.get("avatar_url", ""),
        "created_at": user.get("created_at", "") 
    }

@api_router.put("/users/profile")
async def update_profile(update: ProfileUpdate, authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    db = get_database()
    user = await get_user_by_token(db, token) if db is not None else None
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    update_fields = {}
    if update.name is not None:
        update_fields["name"] = update.name
    if update.avatar_url is not None:
        update_fields["avatar_url"] = update.avatar_url
    
    if update_fields:
        await db.users.update_one(
            {"_id": ObjectId(user["_id"])},
            {"$set": update_fields}
        )
    
    return {"success": True}

@api_router.put("/users/password")
async def change_password(req: PasswordChange, authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    db = get_database()
    user = await get_user_by_token(db, token) if db is not None else None
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not verify_password(req.current_password, user.get("password_hash") or ""):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    await db.users.update_one(
        {"_id": ObjectId(user["_id"])},
        {"$set": {"password_hash": hash_password(req.new_password)}}
    )
    return {"success": True}

@api_router.get("/users/settings")
async def get_settings(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    db = get_database()
    user = await get_user_by_token(db, token) if db is not None else None
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user.get("settings", {})

@api_router.put("/users/settings")
async def update_settings(settings: SettingsUpdate, authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    db = get_database()
    user = await get_user_by_token(db, token) if db is not None else None
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    update_fields = {}
    for field in ['aws_access_key', 'aws_secret_key', 'aws_region', 'openai_api_key', 'openai_model', 'enabled_tools', 'system_prompt']:
        val = getattr(settings, field, None)
        if val is not None:
            update_fields[f"settings.{field}"] = val
    
    if update_fields:
        await db.users.update_one(
            {"_id": ObjectId(user["_id"])},
            {"$set": update_fields}
        )
    return {"success": True}


# ─── WebSocket Notifications (Legacy/Compatibility) ──────────────────────────

@app.websocket("/api/v1/notifications/ws/{client_id}")
async def websocket_notifications(websocket: WebSocket, client_id: str):
    """
    Handle WebSocket connections for notifications.
    Currently a stub to prevent client-side 404 errors/reconnection loops.
    """
    await websocket.accept()
    try:
        while True:
            # Keep connection alive, ignore incoming messages
            await websocket.receive_text()
    except Exception:
        # Connection closed
        pass

# Include the router in the main app
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    # Run the FastAPI app
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
