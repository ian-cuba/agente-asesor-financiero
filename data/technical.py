from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
import yfinance as yf

# Intentar importar pandas_ta; si no está disponible, proveer implementaciones vectorizadas nativas
try:
    import pandas_ta as ta  # type: ignore
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False

from data.schemas import TechnicalIndicators

logger = logging.getLogger(__name__)


def _calculate_rsi_native(series: pd.Series, period: int = 14) -> pd.Series:
    """Cálculo nativo de RSI (Wilder) si pandas-ta no está en el entorno."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0.0)).copy()
    loss = (-delta.where(delta < 0, 0.0)).copy()

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val: Any = 100 - (100 / (1 + rs))
    rsi_series = pd.Series(rsi_val) if not isinstance(rsi_val, pd.Series) else rsi_val
    return rsi_series.fillna(50.0)


def _calculate_atr_native(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Cálculo nativo de Average True Range (ATR)."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    res: Any = tr.rolling(window=period).mean()
    return pd.Series(res) if not isinstance(res, pd.Series) else res


def detect_key_levels(df: pd.DataFrame, window: int = 15, max_levels: int = 3) -> tuple[List[float], List[float]]:
    """
    Detecta soportes y resistencias locales usando máximos y mínimos relativos
    y los filtra en relación al precio de cierre más reciente.
    """
    if len(df) < window * 2:
        return [], []

    highs = df["High"].values
    lows = df["Low"].values
    current_price = float(df["Close"].iloc[-1])

    potential_resistances: List[float] = []
    potential_supports: List[float] = []

    for i in range(window, len(df) - window):
        # Punto pivote alto (Resistencia)
        if highs[i] == max(highs[i - window : i + window + 1]):
            potential_resistances.append(float(highs[i]))
        # Punto pivote bajo (Soporte)
        if lows[i] == min(lows[i - window : i + window + 1]):
            potential_supports.append(float(lows[i]))

    # Filtrar resistencias por encima del precio actual y ordenar de menor a mayor
    valid_resistances = sorted([round(r, 2) for r in set(potential_resistances) if r > current_price * 1.002])
    # Filtrar soportes por debajo del precio actual y ordenar de mayor a menor (más cercano a más lejano)
    valid_supports = sorted([round(s, 2) for s in set(potential_supports) if s < current_price * 0.998], reverse=True)

    # Si no se detectaron suficientes niveles por consolidación, usar percentiles / max / min del último semestre
    last_6m = df.tail(126)
    if not valid_resistances and not last_6m.empty:
        max_6m = float(last_6m["High"].max())
        if max_6m > current_price:
            valid_resistances.append(round(max_6m, 2))

    if not valid_supports and not last_6m.empty:
        min_6m = float(last_6m["Low"].min())
        if min_6m < current_price:
            valid_supports.append(round(min_6m, 2))

    # Contingencia final para activos en máximos o mínimos absolutos
    if not valid_supports:
        valid_supports = [round(current_price * 0.95, 2), round(current_price * 0.90, 2)]
    if not valid_resistances:
        valid_resistances = [round(current_price * 1.05, 2), round(current_price * 1.10, 2)]

    return valid_supports[:max_levels], valid_resistances[:max_levels]


def calculate_technical_indicators(df: pd.DataFrame, ticker: str) -> TechnicalIndicators:
    """Calcula deterministamente indicadores cuantitativos y técnicos sobre un histórico OHLCV."""
    if df.empty:
        raise ValueError(f"Datos históricos vacíos para calcular indicadores de {ticker}")

    # Normalizar columnas numéricas y descartar sesiones incompletas con NaN en Close
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df.dropna(subset=["Close"], inplace=True)
    if len(df) < 50:
        raise ValueError(f"Datos históricos insuficientes para calcular indicadores de {ticker}")

    df["High"] = pd.to_numeric(df["High"], errors="coerce")
    df["Low"] = pd.to_numeric(df["Low"], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")

    work_df = df

    # Medias Móviles Simples
    work_df["SMA_50"] = work_df["Close"].rolling(window=50).mean()
    work_df["SMA_200"] = work_df["Close"].rolling(window=200).mean() if len(work_df) >= 200 else None

    # RSI (14)
    if HAS_PANDAS_TA:
        work_df["RSI_14"] = work_df.ta.rsi(length=14)
        macd_df = work_df.ta.macd(fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            work_df["MACD"] = macd_df.iloc[:, 0]
            work_df["MACD_HIST"] = macd_df.iloc[:, 1]
            work_df["MACD_SIGNAL"] = macd_df.iloc[:, 2]
        else:
            work_df["MACD"] = None
            work_df["MACD_HIST"] = None
            work_df["MACD_SIGNAL"] = None
        work_df["ATR_14"] = work_df.ta.atr(length=14)
    else:
        close_series = pd.Series(work_df["Close"].squeeze())
        work_df["RSI_14"] = _calculate_rsi_native(close_series, period=14)
        work_df["ATR_14"] = _calculate_atr_native(work_df, period=14)
        # MACD nativo
        ema_12 = work_df["Close"].ewm(span=12, adjust=False).mean()
        ema_26 = work_df["Close"].ewm(span=26, adjust=False).mean()
        work_df["MACD"] = ema_12 - ema_26
        work_df["MACD_SIGNAL"] = work_df["MACD"].ewm(span=9, adjust=False).mean()
        work_df["MACD_HIST"] = work_df["MACD"] - work_df["MACD_SIGNAL"]

    last_row = work_df.iloc[-1]
    current_close = float(last_row["Close"])
    sma_50 = float(last_row["SMA_50"]) if pd.notna(last_row["SMA_50"]) else None
    sma_200 = float(last_row["SMA_200"]) if pd.notna(last_row.get("SMA_200")) else None
    rsi_14 = float(last_row["RSI_14"]) if pd.notna(last_row["RSI_14"]) else None
    macd = float(last_row["MACD"]) if pd.notna(last_row["MACD"]) else None
    macd_signal = float(last_row["MACD_SIGNAL"]) if pd.notna(last_row["MACD_SIGNAL"]) else None
    macd_hist = float(last_row["MACD_HIST"]) if pd.notna(last_row["MACD_HIST"]) else None
    atr_14 = float(last_row["ATR_14"]) if pd.notna(last_row["ATR_14"]) else None

    # Distancias porcentuales
    dist_sma50 = round(((current_close - sma_50) / sma_50) * 100, 2) if sma_50 else None
    dist_sma200 = round(((current_close - sma_200) / sma_200) * 100, 2) if sma_200 else None

    # Cruces y Régimen de Tendencia
    golden_cross = False
    death_cross = False
    trend_regime = "SIDEWAYS"

    if sma_50 and sma_200:
        if sma_50 > sma_200:
            golden_cross = True
            if current_close >= sma_50:
                trend_regime = "STRONG_BULLISH"
            else:
                trend_regime = "BULLISH_CORRECTION"
        else:
            death_cross = True
            if current_close <= sma_50:
                trend_regime = "STRONG_BEARISH"
            else:
                trend_regime = "BEARISH_REBOUND"
    elif sma_50:
        trend_regime = "BULLISH" if current_close >= sma_50 else "BEARISH"

    # Soportes y Resistencias
    supports, resistances = detect_key_levels(work_df)

    # Volumen promedio 20 ruedas
    vol_20 = float(work_df["Volume"].tail(20).mean()) if "Volume" in work_df else None

    # Formatear últimas velas (últimos 30 días hábiles)
    recent_tail = work_df.tail(30)
    recent_candles: List[Dict[str, Any]] = []
    for date_idx, row in recent_tail.iterrows():
        idx_val: Any = date_idx
        date_str = idx_val.strftime("%Y-%m-%d") if hasattr(idx_val, "strftime") else str(idx_val)[:10]
        vol_raw: Any = row["Volume"]
        recent_candles.append({
            "date": date_str,
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(float(vol_raw)) if pd.notna(vol_raw) else 0,
        })

    last_idx: Any = work_df.index[-1]
    as_of = (
        last_idx.strftime("%Y-%m-%d")
        if hasattr(last_idx, "strftime")
        else str(last_idx)[:10]
    )

    # Copiar de vuelta las columnas técnicas calculadas al DataFrame original df
    for col in ["SMA_50", "SMA_200", "RSI_14", "MACD", "MACD_SIGNAL", "MACD_HIST", "ATR_14"]:
        if col in work_df:
            df[col] = work_df[col]

    return TechnicalIndicators(
        ticker=ticker.upper(),
        as_of_date=as_of,
        current_close=round(current_close, 2),
        sma_50=round(sma_50, 2) if sma_50 is not None else None,
        sma_200=round(sma_200, 2) if sma_200 is not None else None,
        rsi_14=round(rsi_14, 2) if rsi_14 is not None else None,
        macd=round(macd, 4) if macd is not None else None,
        macd_signal=round(macd_signal, 4) if macd_signal is not None else None,
        macd_histogram=round(macd_hist, 4) if macd_hist is not None else None,
        atr_14=round(atr_14, 2) if atr_14 is not None else None,
        distance_to_sma50_pct=dist_sma50,
        distance_to_sma200_pct=dist_sma200,
        trend_regime=trend_regime,
        golden_cross=golden_cross,
        death_cross=death_cross,
        key_supports=supports,
        key_resistances=resistances,
        daily_volume_avg_20=round(vol_20, 0) if vol_20 is not None else None,
        recent_candles=recent_candles,
    )


def fetch_technical_data(ticker: str, period: str = "2y", interval: str = "1d") -> tuple[pd.DataFrame, TechnicalIndicators]:
    """Descarga cotizaciones históricas y computa los indicadores técnicos."""
    clean_ticker = ticker.strip().upper()
    logger.info(f"Descargando serie técnica para {clean_ticker} (período={period})...")

    yf_ticker = yf.Ticker(clean_ticker)
    df = yf_ticker.history(period=period, interval=interval, auto_adjust=True)

    if df.empty:
        raise ValueError(f"No se pudieron descargar cotizaciones históricas para {clean_ticker}")

    indicators = calculate_technical_indicators(df, clean_ticker)
    return df, indicators


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo_ticker = "MELI"
    df_raw, tech = fetch_technical_data(demo_ticker)
    print(f"\n--- INDICADORES TÉCNICOS DE {tech.ticker} ({tech.as_of_date}) ---")
    print(f"Cierre: ${tech.current_close} | Régimen: {tech.trend_regime}")
    print(f"SMA 50: ${tech.sma_50} ({tech.distance_to_sma50_pct}%) | SMA 200: ${tech.sma_200} ({tech.distance_to_sma200_pct}%)")
    print(f"RSI (14): {tech.rsi_14} | ATR (14): ${tech.atr_14}")
    print(f"Soportes clave: {tech.key_supports}")
    print(f"Resistencias clave: {tech.key_resistances}")
    print(f"Golden Cross activo: {tech.golden_cross} | Death Cross activo: {tech.death_cross}")
