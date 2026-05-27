"""
MCP Schemas - Define contracts for all tools
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import date


class ToolInputSchema(BaseModel):
    """Base schema for tool inputs"""
    pass


class ToolOutputSchema(BaseModel):
    """Base schema for tool outputs"""
    success: bool
    data: Any
    error: Optional[str] = None


class DateRangeInput(ToolInputSchema):
    """Input schema for date range queries"""
    start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    end_date: str = Field(..., description="End date in YYYY-MM-DD format")
    granularity: str = Field(default="DAILY", description="DAILY or MONTHLY")


class ServiceFilterInput(ToolInputSchema):
    """Input schema for service-specific queries"""
    start_date: str
    end_date: str
    service_name: Optional[str] = None


class RegionFilterInput(ToolInputSchema):
    """Input schema for region-specific queries"""
    start_date: str
    end_date: str
    region_name: Optional[str] = None


class AccountFilterInput(ToolInputSchema):
    """Input schema for account-specific queries"""
    start_date: str
    end_date: str
    account_id: Optional[str] = None


class CostOutput(ToolOutputSchema):
    """Output schema for cost queries"""
    total_cost: float
    currency: str = "USD"
    breakdown: Optional[List[Dict[str, Any]]] = None


class ResourceListOutput(ToolOutputSchema):
    """Output schema for resource inventory"""
    resource_type: str
    count: int
    items: List[Dict[str, Any]]
