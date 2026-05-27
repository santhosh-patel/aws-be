from typing import Optional, Tuple
import re
from datetime import date, datetime, timedelta
from app.planner.models import DateRange

class DeterministicTimeParser:
    """
    Parses relative time expressions into strict DateRange objects.
    Bypasses LLM for common patterns to ensure accuracy.
    """
    
    def parse(self, query: str) -> Optional[Tuple[DateRange, str, str]]:
        """
        Parse query for time ranges.
        Returns (DateRange, raw_match, normalized_key) or None.
        """
        query_lower = query.lower()
        today = date.today()
        
        # Next X Months/Weeks (Forecast)
        match = re.search(r'\bnext\s+(\d+)\s+(month|week)s?\b', query_lower)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            start = today
            if unit == 'month':
                # Approx 30 days per month
                end = today + timedelta(days=amount * 30)
                return DateRange(start_date=start, end_date=end), match.group(0), f"next_{amount}_{unit}s"
            elif unit == 'week':
                end = today + timedelta(weeks=amount)
                return DateRange(start_date=start, end_date=end), match.group(0), f"next_{amount}_{unit}s"

        # Last/Past X Months/Weeks/Days
        match = re.search(r'\b(last|past)\s+(\d+)\s+(month|week|day)s?\b', query_lower)
        if match:
            amount = int(match.group(2))
            unit = match.group(3)
            end = today
            if unit == 'month':
                start = today - timedelta(days=amount * 30)
                return DateRange(start_date=start, end_date=end), match.group(0), f"last_{amount}_{unit}s"
            elif unit == 'week':
                start = today - timedelta(weeks=amount)
                return DateRange(start_date=start, end_date=end), match.group(0), f"last_{amount}_{unit}s"
            elif unit == 'day':
                start = today - timedelta(days=amount)
                return DateRange(start_date=start, end_date=end), match.group(0), f"last_{amount}_{unit}s"

        # Static Keywords
        if 'yesterday' in query_lower:
            yesterday = today - timedelta(days=1)
            return DateRange(start_date=yesterday, end_date=yesterday), 'yesterday', 'yesterday'
            
        if 'today' in query_lower:
            return DateRange(start_date=today, end_date=today), 'today', 'today'
            
        if 'last month' in query_lower:
            start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            end = today.replace(day=1) - timedelta(days=1)
            return DateRange(start_date=start, end_date=end), 'last month', 'last_month'

        # Recent / Past N Months (e.g. "recent months", "past 3 months", "last few months")
        match = re.search(r'\b(recent|past|last)\s+(?:few|couple)?\s*months?\b', query_lower)
        if match:
             # Default "recent months" to last 3 months if number not specified
             # If number specified, handled by "last X months" regex above?
             # My regex above: r'\b(last|past)\s+(\d+)\s+(month|week|day)s?\b'
             # It requires a digit. 
             # Need to handle "last few months" -> 3 months?
             amount = 3
             start = today - timedelta(days=amount * 30)
             end = today
             return DateRange(start_date=start, end_date=end), match.group(0), "last_3_months"

        # Past/Last Quarter (Specific check for "past quarter" which might be missed by strict "last quarter")
        # Current regex: r'\b(next|last|past|this)\s+quarter\b' - This covers it.
        
        # Last N Quarters
        match = re.search(r'\b(last|past)\s+(\d+)\s+quarters?\b', query_lower)
        if match:
            amount = int(match.group(2))
            # 1 quarter = 90 days
            start = today - timedelta(days=amount * 90)
            end = today
            return DateRange(start_date=start, end_date=end), match.group(0), f"last_{amount}_quarters"
            
        # Year to Date / This Year
        if 'this year' in query_lower or 'year to date' in query_lower or 'ytd' in query_lower:
            start = date(today.year, 1, 1)
            return DateRange(start_date=start, end_date=today), 'this year', 'year_to_date'

        if 'current month' in query_lower or 'this month' in query_lower:
            start = today.replace(day=1)
            return DateRange(start_date=start, end_date=today), 'this month', 'current_month'

        # Quarters
        match = re.search(r'\b(next|last|past|this)\s+quarter\b', query_lower)
        if match:
            direction = match.group(1)
            # Simplified: Treat quarter as 3 months for relative calculation
            # Production would find actual Q1/Q2/Q3/Q4 dates
            if direction == 'next':
                start = today
                end = today + timedelta(days=90)
                return DateRange(start_date=start, end_date=end), match.group(0), "next_quarter"
            elif direction in ['last', 'past']:
                end = today
                start = today - timedelta(days=90)
                return DateRange(start_date=start, end_date=end), match.group(0), "last_quarter"
            elif direction == 'this':
                start = today - timedelta(days=45) # Approx mid-point
                end = today + timedelta(days=45)
                return DateRange(start_date=start, end_date=end), match.group(0), "current_quarter"

        if 'next month' in query_lower:
            # First day of next month
            if today.month == 12:
                start = date(today.year + 1, 1, 1)
            else:
                start = date(today.year, today.month + 1, 1)
            end = start + timedelta(days=30) # Approx
            return DateRange(start_date=start, end_date=end), 'next month', 'next_month'

        return None
