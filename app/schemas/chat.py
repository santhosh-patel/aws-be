from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class MessageBase(BaseModel):
    role: str
    content: Any # Can be string or structured JSON/dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatBase(BaseModel):
    title: str = "New Chat"
    user_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ChatCreate(BaseModel):
    title: Optional[str] = "New Chat"

class ChatResponseModel(ChatBase):
    id: str = Field(alias="_id")

    class Config:
        populate_by_name = True

class MessageResponseModel(MessageBase):
    id: str = Field(alias="_id")
    chat_id: str

    class Config:
        populate_by_name = True
