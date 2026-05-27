"""
Response Schemas - Strict contracts for frontend rendering
LLM must never decide presentation - only return structured data
"""
from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel, Field, validator


class TimeRange(BaseModel):
    """Date range for cost queries"""
    start: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    end: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')


class CostSummaryResponse(BaseModel):
    """
    Used for: today, yesterday, current month total
    Frontend renders as: Stat card
    """
    type: Literal["COST_SUMMARY"] = "COST_SUMMARY"
    label: str = Field(..., description="Human-readable label like 'Current month'")
    time_range: TimeRange
    currency: str = "USD"
    total_cost: float = Field(..., ge=0)
    data_freshness_note: str = "Cost Explorer data may lag by up to 48 hours"


class BreakdownItem(BaseModel):
    """Single item in a cost breakdown"""
    name: str
    cost: float = Field(..., ge=0)


class CostBreakdownResponse(BaseModel):
    """
    Used for: cost by service, region, account
    Frontend renders as: Table + optional pie chart
    """
    type: Literal["COST_BREAKDOWN"] = "COST_BREAKDOWN"
    dimension: Literal["SERVICE", "REGION", "ACCOUNT"]
    time_range: TimeRange
    currency: str = "USD"
    total_cost: float = Field(..., ge=0)
    breakdown: List[BreakdownItem] = Field(..., min_items=0)


class TimeSeriesPoint(BaseModel):
    """Single point in time series"""
    date: str = Field(..., pattern=r'^\d{4}-\d{2}(-\d{2})?$')  # YYYY-MM or YYYY-MM-DD
    cost: float = Field(..., ge=0)


class CostTimeSeriesResponse(BaseModel):
    """
    Used for: historical data, trends, last 12 months
    Frontend renders as: Line or bar chart
    """
    type: Literal["COST_TIME_SERIES"] = "COST_TIME_SERIES"
    granularity: Literal["DAILY", "MONTHLY"]
    currency: str = "USD"
    time_range: TimeRange
    total_cost: float = Field(..., ge=0)
    points: List[TimeSeriesPoint] = Field(..., min_items=0)


class ResourceItem(BaseModel):
    """Single resource in inventory"""
    id: str
    type: str
    name: Optional[str] = None
    region: Optional[str] = None
    state: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ResourceListResponse(BaseModel):
    """
    Used for: EC2 instances, S3 buckets, etc.
    Frontend renders as: Table
    """
    type: Literal["RESOURCE_LIST"] = "RESOURCE_LIST"
    resource_type: str
    count: int = Field(..., ge=0)
    resources: List[ResourceItem] = Field(..., min_items=0)


class ErrorStateResponse(BaseModel):
    """
    Used for: unsupported time range, missing permissions, empty data
    Frontend renders as: Error message block
    """
    type: Literal["ERROR_STATE"] = "ERROR_STATE"
    error_code: Literal[
        "UNSUPPORTED_TIME_RANGE",
        "MISSING_PERMISSION",
        "NO_DATA",
        "INVALID_INPUT",
        "AWS_ERROR",
        "UNKNOWN_ERROR"
    ]
    message: str
    suggestion: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


# Union type for all possible responses
ResponseType = CostSummaryResponse | CostBreakdownResponse | CostTimeSeriesResponse | ResourceListResponse | ErrorStateResponse


def validate_response_schema(response_data: Dict[str, Any]) -> bool:
    """Validate that response matches one of the required schemas"""
    response_type = response_data.get("type")
    
    schema_map = {
        "COST_SUMMARY": CostSummaryResponse,
        "COST_BREAKDOWN": CostBreakdownResponse,
        "COST_TIME_SERIES": CostTimeSeriesResponse,
        "RESOURCE_LIST": ResourceListResponse,
        "ERROR_STATE": ErrorStateResponse
    }
    
    schema_class = schema_map.get(response_type)
    if not schema_class:
        return False
    
    try:
        schema_class(**response_data)
        return True
    except Exception:
        return False
