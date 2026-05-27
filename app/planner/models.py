from __future__ import annotations
from typing import List, Optional, Literal, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime

class DateRange(BaseModel):
    start_date: date
    end_date: date

    @field_validator('end_date')
    def end_date_must_be_after_start_date(cls, v, values):
        if 'start_date' in values.data and v < values.data['start_date']:
            raise ValueError('end_date must be after start_date')
        return v

class CostQueryParams(BaseModel):
    time_range: DateRange
    granularity: Literal['DAILY', 'MONTHLY'] = 'MONTHLY'
    filter_service: Optional[str] = None
    filter_region: Optional[str] = None
    filter_account_id: Optional[str] = None
    filter_usage_type: Optional[str] = None
    filter_tag: Optional[str] = None
    group_by: Optional[Literal['SERVICE', 'REGION', 'LINKED_ACCOUNT', 'USAGE_TYPE', 'TAG']] = None

class ResourceQueryParams(BaseModel):
    service: str
    region: Optional[str] = None

class CanonicalIntent(BaseModel):
    intent: Literal[
        'COST_TOTAL',
        'COST_BY_SERVICE',
        'COST_BY_REGION',
        'COST_BY_ACCOUNT',
        'COST_BY_USAGE_TYPE',
        'COST_BY_TAG',
        'COST_TREND',
        'COST_FORECAST',
        'COST_ANOMALY',
        'COST_COMPARE',
        'RESOURCE_INVENTORY',
        'ACCOUNT_METADATA',
        'ACCOUNT_OVERVIEW',
        'COMPREHENSIVE_COST',
        'SERVICE_DEEP_DIVE',
        'CLOUDWATCH_METRICS',
        'LOG_EVENTS',
        'GREETING',
        'CONVERSATIONAL',
        'AWS_KNOWLEDGE',
        'UNSUPPORTED',
        'UNKNOWN'
    ]
    time_range: Optional[DateRange] = None
    services: List[str] = Field(default_factory=list)
    regions: List[str] = Field(default_factory=list)
    comparison: Optional[Literal['time', 'service', 'region']] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0

class PlanStep(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    description: str

class ExecutionPlan(BaseModel):
    intent: CanonicalIntent
    steps: List[PlanStep]
    user_query: str
    explanation: str

class SkillRoute(BaseModel):
    skill: Literal[
        'cost_query',
        'resource_inventory',
        'account_info',
        'overview',
        'aws_knowledge',
        'greeting',
        'conversational',
        'unsupported',
        'clarification_needed'
    ]
    confidence: float
