"""
Analytics & Insights Engine — Converts raw AWS data into actionable intelligence.

Components:
  - rules.py       : Individual rule functions that detect patterns
  - insights_engine : Orchestrator that runs rules against tool results
"""
from .insights_engine import InsightsEngine
from .rules import Insight

__all__ = ["InsightsEngine", "Insight"]
