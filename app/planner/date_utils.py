"""
Date Utilities - Centralized date handling following AWS Cost Explorer conventions
AWS Cost Explorer: start=inclusive, end=exclusive
"""
from datetime import datetime, timedelta
from typing import Tuple


def get_full_month_range(year: int, month: int) -> Tuple[str, str]:
    """
    Get full month date range following AWS conventions.
    
    AWS Cost Explorer uses:
    - start: inclusive (first day of month)
    - end: exclusive (first day of next month)
    
    Args:
        year: Year (e.g., 2024)
        month: Month (1-12)
        
    Returns:
        Tuple of (start_date, end_date) in 'YYYY-MM-DD' format
    """
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')


def get_last_n_months_range(n: int) -> Tuple[str, str]:
    """
    Get date range for last N complete months.
    
    Args:
        n: Number of months to go back
        
    Returns:
        Tuple of (start_date, end_date) in 'YYYY-MM-DD' format
    """
    today = datetime.now()
    # Go to first day of current month
    current_month_start = today.replace(day=1)
    
    # Calculate start date (N months back from current month start)
    months_back = n
    year = current_month_start.year
    month = current_month_start.month
    
    while months_back > 0:
        month -= 1
        if month < 1:
            month = 12
            year -= 1
        months_back -= 1
    
    start = datetime(year, month, 1)
    end = current_month_start  # Exclusive
    
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')


def get_last_n_days_range(n: int) -> Tuple[str, str]:
    """
    Get date range for last N days (not including today).
    
    Args:
        n: Number of days to go back
        
    Returns:
        Tuple of (start_date, end_date) in 'YYYY-MM-DD' format
    """
    today = datetime.now()
    end = today  # Exclusive (so yesterday is included)
    start = today - timedelta(days=n)
    
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')


def validate_date_range_within_14_months(start_date: str, end_date: str) -> Tuple[bool, str]:
    """
    Validate that date range is within AWS Cost Explorer's 14-month limit.
    
    Args:
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        # AWS Cost Explorer retains 14 months of data
        max_days = 14 * 31  # Conservative estimate (434 days)
        
        days_diff = (end - start).days
        
        if days_diff > max_days:
            return False, f"Date range exceeds AWS Cost Explorer's 14-month limit ({days_diff} days requested, {max_days} days maximum)"
        
        # Also check if start date is too far in the past
        today = datetime.now()
        days_from_today = (today - start).days
        
        if days_from_today > max_days:
            return False, f"Start date is beyond AWS Cost Explorer's 14-month retention ({days_from_today} days ago)"
        
        return True, ""
        
    except ValueError as e:
        return False, f"Invalid date format: {str(e)}"


def get_current_month_range() -> Tuple[str, str]:
    """
    Get date range for current month (month-to-date).
    
    Returns:
        Tuple of (start_date, end_date) in 'YYYY-MM-DD' format
    """
    today = datetime.now()
    month_start = today.replace(day=1)
    # End is tomorrow to include today (AWS uses exclusive end)
    tomorrow = today + timedelta(days=1)
    
    return month_start.strftime('%Y-%m-%d'), tomorrow.strftime('%Y-%m-%d')


def get_today_range() -> Tuple[str, str]:
    """
    Get date range for today.
    
    Returns:
        Tuple of (start_date, end_date) in 'YYYY-MM-DD' format
    """
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    
    return today.strftime('%Y-%m-%d'), tomorrow.strftime('%Y-%m-%d')


def get_yesterday_range() -> Tuple[str, str]:
    """
    Get date range for yesterday.
    
    Returns:
        Tuple of (start_date, end_date) in 'YYYY-MM-DD' format
    """
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    
    return yesterday.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')
