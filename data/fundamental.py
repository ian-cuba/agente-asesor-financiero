from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
import numpy as np
import pandas as pd
import yfinance as yf

from config import get_cedear_ratio
from data.schemas import FundamentalProfile, ValuationMetrics, AnnualFinancialRecord

logger = logging.getLogger(__name__)


def _clean_numeric(value: Any) -> Optional[float]:
    """Limpia y valida un número, soportando Series, arrays, NaN e Inf con conversión a float nativo."""
    if value is None:
        return None
    # Si por duplicidad de índices en yfinance se recibe una Serie o array, extraer el primer escalar
    if isinstance(value, (pd.Series, np.ndarray, list)):
        if len(value) == 0:
            return None
        if isinstance(value, pd.Series):
            value = value.dropna().iloc[0] if not value.dropna().empty else None
        elif isinstance(value, list):
            value = value[0]
        else:
            value = value.flat[0]
    
    if value is None or pd.isna(value):
        return None
    try:
        val = float(value)
        if np.isnan(val) or np.isinf(val):
            return None
        return val
    except (ValueError, TypeError):
        return None


def _clean_round(value: Any, decimals: int = 1) -> Optional[float]:
    """Limpia un valor numérico y lo redondea a la cantidad especificada de decimales."""
    val = _clean_numeric(value)
    return round(val, decimals) if val is not None else None


def _get_row_value(df: pd.DataFrame, field_candidates: List[str], col_name: Any) -> Optional[float]:
    """Busca el valor de una fila en un DataFrame según una lista de nombres de conceptos contables posibles."""
    if df is None or df.empty or col_name not in df.columns:
        return None
    
    for candidate in field_candidates:
        matches = [idx for idx in df.index if candidate.lower() in str(idx).lower()]
        if matches:
            val = df.loc[matches[0], col_name]
            cleaned = _clean_numeric(val)
            if cleaned is not None:
                return cleaned
    return None


def extract_annual_financials(ticker_obj: yf.Ticker, max_years: int = 5) -> List[AnnualFinancialRecord]:
    """Extrae el historial financiero anual consolidado (Ingresos, Ganancia Neta, EPS, Capex, FCF)."""
    records: List[AnnualFinancialRecord] = []

    try:
        income_stmt = ticker_obj.income_stmt
        if income_stmt is None or income_stmt.empty:
            income_stmt = ticker_obj.financials

        cash_flow = ticker_obj.cash_flow
        if cash_flow is None or cash_flow.empty:
            cash_flow = ticker_obj.cashflow
    except Exception as e:
        logger.warning(f"Error accediendo a estados financieros anuales: {e}")
        return records

    if income_stmt is None or income_stmt.empty:
        return records

    columns = list(income_stmt.columns)[:max_years]
    # Invertir para orden cronológico ascendente (ej: 2022 -> 2025)
    columns.reverse()

    for col in columns:
        year_str = str(col.year) if hasattr(col, "year") else str(col)[:4]

        revenue = _get_row_value(income_stmt, ["Total Revenue", "Operating Revenue", "Revenue"], col)
        net_income = _get_row_value(income_stmt, ["Net Income Common Stockholders", "Net Income", "Normalized Income"], col)
        eps = _get_row_value(income_stmt, ["Diluted EPS", "Basic EPS", "EPS"], col)

        # Si el año no tiene ningún dato relevante (ej. columnas futuras o pasadas vacías), omitir
        if revenue is None and net_income is None and eps is None:
            continue

        # Flujos de fondos (si están disponibles para el mismo ejercicio)
        ocf = None
        capex = None
        fcf = None
        if cash_flow is not None and not cash_flow.empty:
            matching_cf_cols = [c for c in cash_flow.columns if (hasattr(c, "year") and str(c.year) == year_str) or str(c)[:4] == year_str]
            if matching_cf_cols:
                cf_col = matching_cf_cols[0]
                ocf = _get_row_value(cash_flow, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], cf_col)
                capex = _get_row_value(cash_flow, ["Capital Expenditure", "Purchase Of PPE"], cf_col)
                if capex is not None and capex < 0:
                    capex = abs(capex)
                if ocf is not None and capex is not None:
                    fcf = ocf - capex

        records.append(
            AnnualFinancialRecord(
                year=year_str,
                revenue=revenue,
                net_income=net_income,
                eps=eps,
                operating_cash_flow=ocf,
                capex=capex,
                free_cash_flow=fcf,
            )
        )

    return records


def fetch_fundamental_data(ticker: str) -> FundamentalProfile:
    """Descarga y estructura las métricas contables, perfil de negocio y valuación de un ticker."""
    clean_ticker = ticker.strip().upper()
    logger.info(f"Obteniendo datos fundamentales para: {clean_ticker}")

    yf_ticker = yf.Ticker(clean_ticker)
    info: Dict[str, Any] = {}
    try:
        info = yf_ticker.info or {}
    except Exception as e:
        logger.warning(f"No se pudo descargar info completa para {clean_ticker}: {e}")

    fast_info = getattr(yf_ticker, "fast_info", None)

    current_price = (
        _clean_numeric(info.get("currentPrice"))
        or _clean_numeric(info.get("regularMarketPrice"))
        or _clean_numeric(info.get("previousClose"))
        or (_clean_numeric(getattr(fast_info, "last_price", None)) if fast_info else None)
        or 0.0
    )

    market_cap = _clean_numeric(info.get("marketCap"))
    if market_cap is None and fast_info:
        market_cap = _clean_numeric(getattr(fast_info, "market_cap", None))

    valuation = ValuationMetrics(
        market_cap=market_cap,
        enterprise_value=_clean_numeric(info.get("enterpriseValue")),
        trailing_pe=_clean_round(info.get("trailingPE"), 1),
        forward_pe=_clean_round(info.get("forwardPE"), 1),
        peg_ratio=_clean_round(info.get("pegRatio"), 1),
        price_to_book=_clean_round(info.get("priceToBook"), 1),
        ev_to_ebitda=_clean_round(info.get("enterpriseToEbitda"), 1),
        dividend_yield=_clean_numeric(info.get("dividendYield")),
        currency=str(info.get("currency") or (getattr(fast_info, "currency", None) if fast_info else "USD")),
    )

    history_records = extract_annual_financials(yf_ticker)

    profile = FundamentalProfile(
        ticker=clean_ticker,
        company_name=str(info.get("longName") or info.get("shortName") or clean_ticker),
        sector=str(info.get("sector", "N/A")),
        industry=str(info.get("industry", "N/A")),
        country=str(info.get("country", "N/A")),
        business_summary=str(info.get("longBusinessSummary", "No hay resumen de negocio disponible.")),
        current_price=current_price,
        fifty_two_week_high=_clean_numeric(info.get("fiftyTwoWeekHigh")),
        fifty_two_week_low=_clean_numeric(info.get("fiftyTwoWeekLow")),
        target_mean_price=_clean_numeric(info.get("targetMeanPrice")),
        target_high_price=_clean_numeric(info.get("targetHighPrice")),
        target_low_price=_clean_numeric(info.get("targetLowPrice")),
        recommendation_key=info.get("recommendationKey"),
        analyst_count=info.get("numberOfAnalystOpinions"),
        cedear_ratio=get_cedear_ratio(clean_ticker),
        valuation=valuation,
        financial_history=history_records,
        gross_margin=_clean_numeric(info.get("grossMargins")),
        operating_margin=_clean_numeric(info.get("operatingMargins")),
        net_margin=_clean_numeric(info.get("profitMargins")),
        roe=_clean_numeric(info.get("returnOnEquity")),
        total_debt=_clean_numeric(info.get("totalDebt")),
        total_cash=_clean_numeric(info.get("totalCash")),
        debt_to_equity=_clean_numeric(info.get("debtToEquity")),
    )

    return profile


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo_ticker = "MELI"
    data = fetch_fundamental_data(demo_ticker)
    print(f"\n--- PERFIL FUNDAMENTAL DE {data.ticker} ({data.company_name}) ---")
    print(f"Sector: {data.sector} | Industria: {data.industry}")
    print(f"Precio actual: ${data.current_price:.2f} | Ratio CEDEAR: {data.cedear_ratio}")
    print(f"P/E Trailing: {data.valuation.trailing_pe} | P/E Forward: {data.valuation.forward_pe}")
    print(f"Margen Neto: {data.net_margin} | Deuda Neta / Equity: {data.debt_to_equity}")
    print(f"Historial contable ({len(data.financial_history)} años):")
    for rec in data.financial_history:
        rev_str = f"${rec.revenue:,.0f}" if rec.revenue else "N/A"
        eps_str = f"${rec.eps:.2f}" if rec.eps else "N/A"
        print(f"  Año {rec.year}: Ingresos={rev_str} | EPS={eps_str}")
