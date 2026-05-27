"""
Insights Engine — Orchestrates rule-based analysis on tool execution results.

Runs all applicable rules against a response and returns a list of Insight objects.
Integrated into the chat pipeline: runs after tool execution, before response delivery.
"""
import logging
from typing import Any, Dict, List, Optional

from .rules import (
    Insight,
    detect_cost_anomalies,
    detect_cost_concentration,
    analyze_trends,
    detect_unused_resources,
    suggest_optimizations,
)

logger = logging.getLogger(__name__)

# Map response types to applicable rules
RULES_BY_TYPE = {
    "COST_SUMMARY": [detect_cost_anomalies],
    "COST_BREAKDOWN": [detect_cost_anomalies, detect_cost_concentration, suggest_optimizations],
    "COST_TIME_SERIES": [detect_cost_anomalies, analyze_trends],
    "RESOURCE_LIST": [detect_unused_resources],
}


class InsightsEngine:
    """
    Analyzes tool results and produces actionable insights.
    
    Usage:
        engine = InsightsEngine()
        insights = engine.analyze(response_dict, history=previous_snapshots)
        # insights = [Insight(...), Insight(...), ...]
    """

    def __init__(self, max_insights: int = 5):
        """
        Args:
            max_insights: Maximum insights to return per analysis (avoids noise).
        """
        self.max_insights = max_insights

    def analyze(
        self,
        response: Dict[str, Any],
        history: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        Run all applicable rules against the response.
        
        Args:
            response: The structured response dict (with 'type' field)
            history:  Previous cost snapshots for comparison (optional)
        
        Returns:
            List of Insight dicts, sorted by severity (critical > warning > info)
        """
        if not response or not isinstance(response, dict):
            return []

        resp_type = response.get("type", "")
        rules = RULES_BY_TYPE.get(resp_type, [])

        if not rules:
            return []

        all_insights: List[Insight] = []

        for rule_fn in rules:
            try:
                if rule_fn == detect_cost_anomalies:
                    results = rule_fn(response, history)
                else:
                    results = rule_fn(response)
                all_insights.extend(results)
            except Exception as e:
                logger.warning(f"[Insights] Rule {rule_fn.__name__} failed: {e}")

        # Sort by severity priority
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        all_insights.sort(key=lambda i: severity_order.get(i.severity, 99))

        # Limit to max_insights
        top_insights = all_insights[:self.max_insights]

        if top_insights:
            titles = [i.title for i in top_insights]
            logger.info(f"[Insights] Generated {len(top_insights)} insight(s): {titles}")

        return [i.to_dict() for i in top_insights]

    def analyze_composite(
        self,
        responses: List[Dict[str, Any]],
        history: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        Analyze multiple responses (e.g., from COMPOSITE_RESPONSE).
        Deduplicates insights across sub-responses.
        """
        all_insights = []
        seen_titles = set()

        for resp in responses:
            insights = self.analyze(resp, history)
            for insight in insights:
                if insight["title"] not in seen_titles:
                    all_insights.append(insight)
                    seen_titles.add(insight["title"])

        return all_insights[:self.max_insights]
