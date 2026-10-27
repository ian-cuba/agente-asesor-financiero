from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AnnualFinancialRecord(BaseModel):
    """Métricas contables anuales consolidadas para un ejercicio fiscal."""
    year: str = Field(description="Ejercicio fiscal (ej. '2023')")
    revenue: Optional[float] = Field(default=None, description="Ingresos totales en USD")
    net_income: Optional[float] = Field(default=None, description="Ganancia neta en USD")
    eps: Optional[float] = Field(default=None, description="Ganancias por acción diluida")
    operating_cash_flow: Optional[float] = Field(default=None, description="Flujo de caja operativo")
    capex: Optional[float] = Field(default=None, description="Gastos de capital (Capex)")
    free_cash_flow: Optional[float] = Field(default=None, description="Flujo de caja libre (OCF - Capex)")


class ValuationMetrics(BaseModel):
    """Múltiplos de valuación relativa y valor de mercado."""
    market_cap: Optional[float] = Field(default=None, description="Capitalización bursátil")
    enterprise_value: Optional[float] = Field(default=None, description="Enterprise Value")
    trailing_pe: Optional[float] = Field(default=None, description="P/E Trailing (últimos 12 meses)")
    forward_pe: Optional[float] = Field(default=None, description="P/E Forward proyectado")
    peg_ratio: Optional[float] = Field(default=None, description="Ratio PEG")
    price_to_book: Optional[float] = Field(default=None, description="Precio / Valor libro (P/B)")
    ev_to_ebitda: Optional[float] = Field(default=None, description="EV / EBITDA")
    dividend_yield: Optional[float] = Field(default=None, description="Rendimiento por dividendos")
    currency: str = Field(default="USD", description="Moneda de cotización principal")


class FundamentalProfile(BaseModel):
    """Perfil fundamental y contable completo del activo."""
    ticker: str
    company_name: str
    sector: str
    industry: str
    country: str
    business_summary: str
    current_price: float
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    target_mean_price: Optional[float] = None
    target_high_price: Optional[float] = None
    target_low_price: Optional[float] = None
    recommendation_key: Optional[str] = None
    analyst_count: Optional[int] = None
    cedear_ratio: Optional[float] = None
    valuation: ValuationMetrics
    financial_history: List[AnnualFinancialRecord] = Field(default_factory=list)
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    roe: Optional[float] = None
    total_debt: Optional[float] = None
    total_cash: Optional[float] = None
    debt_to_equity: Optional[float] = None


class TechnicalIndicators(BaseModel):
    """Métricas técnicas calculadas de forma determinista."""
    ticker: str
    as_of_date: str
    current_close: float
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    atr_14: Optional[float] = None
    distance_to_sma50_pct: Optional[float] = None
    distance_to_sma200_pct: Optional[float] = None
    trend_regime: str = Field(description="Régimen de tendencia: 'BULLISH', 'BEARISH', 'SIDEWAYS', 'GOLDEN_CROSS'")
    golden_cross: bool = False
    death_cross: bool = False
    key_supports: List[float] = Field(default_factory=list, description="Soportes técnicos detectados")
    key_resistances: List[float] = Field(default_factory=list, description="Resistencias técnicas detectadas")
    daily_volume_avg_20: Optional[float] = None
    recent_candles: List[Dict[str, Any]] = Field(default_factory=list, description="Velas recientes para gráficos/resumen")


class AssetPayload(BaseModel):
    """Contenedor integral con los datos financieros consolidados del activo para los motores de análisis y reporte."""
    ticker: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fundamentals: FundamentalProfile
    technicals: TechnicalIndicators
