"""
Currency Converter - Deterministic currency conversion with real exchange rates
Uses exchangerate-api.io with 24-hour caching
"""
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import requests
from dataclasses import dataclass
import threading


@dataclass
class ExchangeRate:
    """Exchange rate data"""
    base_currency: str
    target_currency: str
    rate: float
    source: str
    timestamp: datetime
    
    def is_expired(self, ttl_hours: int = 24) -> bool:
        """Check if rate is expired"""
        expiry = self.timestamp + timedelta(hours=ttl_hours)
        return datetime.utcnow() > expiry


class CurrencyConverter:
    """Convert currencies using real exchange rates"""
    
    # Primary API
    API_URL = "https://api.exchangerate-api.com/v4/latest/{base}"
    
    # Fallback rates (updated manually, used when API fails)
    FALLBACK_RATES = {
        'USD': {
            'INR': 83.0,
            'EUR': 0.92,
            'GBP': 0.79,
            'JPY': 149.5,
            'CNY': 7.24,
        }
    }
    
    def __init__(self, cache_ttl_hours: int = 24):
        self.cache: Dict[str, ExchangeRate] = {}
        self.cache_ttl_hours = cache_ttl_hours
        self.lock = threading.Lock()
    
    def convert(
        self,
        amount: float,
        from_currency: str = 'USD',
        to_currency: str = 'INR'
    ) -> Tuple[float, ExchangeRate]:
        """
        Convert amount from one currency to another.
        
        Args:
            amount: Amount to convert
            from_currency: Source currency code (e.g., 'USD')
            to_currency: Target currency code (e.g., 'INR')
            
        Returns:
            Tuple of (converted_amount, exchange_rate_info)
        """
        # Same currency - no conversion needed
        if from_currency == to_currency:
            rate_info = ExchangeRate(
                base_currency=from_currency,
                target_currency=to_currency,
                rate=1.0,
                source='Same currency',
                timestamp=datetime.utcnow()
            )
            return amount, rate_info
        
        # Get exchange rate
        rate_info = self._get_exchange_rate(from_currency, to_currency)
        
        # Convert
        converted_amount = amount * rate_info.rate
        
        return round(converted_amount, 2), rate_info
    
    def _get_exchange_rate(self, base: str, target: str) -> ExchangeRate:
        """
        Get exchange rate from cache or API.
        
        Args:
            base: Base currency
            target: Target currency
            
        Returns:
            ExchangeRate object
        """
        cache_key = f"{base}_{target}"
        
        with self.lock:
            # Check cache
            if cache_key in self.cache:
                cached_rate = self.cache[cache_key]
                if not cached_rate.is_expired(self.cache_ttl_hours):
                    return cached_rate
            
            # Fetch from API
            try:
                rate_info = self._fetch_from_api(base, target)
                self.cache[cache_key] = rate_info
                return rate_info
            except Exception as e:
                print(f"WARN: Exchange rate API failed: {e}, using fallback")
                # Use fallback
                rate_info = self._get_fallback_rate(base, target)
                return rate_info
    
    def _fetch_from_api(self, base: str, target: str) -> ExchangeRate:
        """
        Fetch exchange rate from API.
        
        Args:
            base: Base currency
            target: Target currency
            
        Returns:
            ExchangeRate object
            
        Raises:
            Exception if API request fails
        """
        url = self.API_URL.format(base=base)
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        rates = data.get('rates', {})
        
        if target not in rates:
            raise ValueError(f"Rate for {target} not found in API response")
        
        rate = float(rates[target])
        
        return ExchangeRate(
            base_currency=base,
            target_currency=target,
            rate=rate,
            source=f"exchangerate-api.com {datetime.utcnow().strftime('%Y-%m-%d')}",
            timestamp=datetime.utcnow()
        )
    
    def _get_fallback_rate(self, base: str, target: str) -> ExchangeRate:
        """
        Get fallback exchange rate.
        
        Args:
            base: Base currency
            target: Target currency
            
        Returns:
            ExchangeRate object
        """
        if base in self.FALLBACK_RATES and target in self.FALLBACK_RATES[base]:
            rate = self.FALLBACK_RATES[base][target]
        else:
            # Default to 1.0 if not found
            rate = 1.0
        
        return ExchangeRate(
            base_currency=base,
            target_currency=target,
            rate=rate,
            source=f"Fallback rate (updated manually)",
            timestamp=datetime.utcnow()
        )
    
    def format_conversion(
        self,
        original_amount: float,
        converted_amount: float,
        rate_info: ExchangeRate
    ) -> str:
        """
        Format conversion for display.
        
        Args:
            original_amount: Original amount
            converted_amount: Converted amount
            rate_info: Exchange rate info
            
        Returns:
            Formatted string
        """
        return (
            f"{original_amount:,.2f} {rate_info.base_currency} = "
            f"{converted_amount:,.2f} {rate_info.target_currency} "
            f"(rate: {rate_info.rate:.4f}, source: {rate_info.source})"
        )


# Global instance
_currency_converter: Optional[CurrencyConverter] = None


def get_currency_converter() -> CurrencyConverter:
    """Get global currency converter instance"""
    global _currency_converter
    if _currency_converter is None:
        _currency_converter = CurrencyConverter()
    return _currency_converter
