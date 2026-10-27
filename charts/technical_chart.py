from __future__ import annotations
from pathlib import Path
import logging
from typing import Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

from config import GENERATED_CHARTS_DIR
from data.schemas import TechnicalIndicators

logger = logging.getLogger(__name__)


def generate_technical_chart(
    df: pd.DataFrame,
    technicals: TechnicalIndicators,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Genera un gráfico técnico institucional estilizado de 2 paneles (Precio + Medias / RSI)
    y lo guarda en formato PNG de alta resolución.
    """
    ticker = technicals.ticker.upper()
    dest_path = output_path or (GENERATED_CHARTS_DIR / f"{ticker}_technical.png")

    logger.info(f"Generando gráfico técnico para {ticker} en {dest_path}...")

    # Usar las últimas 180 ruedas para un gráfico limpio y enfocado
    chart_df = df.tail(180).copy()
    if not isinstance(chart_df.index, pd.DatetimeIndex):
        chart_df.index = pd.to_datetime(chart_df.index)

    # Asegurar indicadores técnicos en chart_df si no estuvieran presentes
    if "SMA_50" not in chart_df or chart_df["SMA_50"].dropna().empty:
        chart_df["SMA_50"] = chart_df["Close"].rolling(window=50, min_periods=10).mean()
    if ("SMA_200" not in chart_df or chart_df["SMA_200"].dropna().empty) and len(chart_df) >= 120:
        chart_df["SMA_200"] = chart_df["Close"].rolling(window=200, min_periods=30).mean()
    if "RSI_14" not in chart_df or chart_df["RSI_14"].dropna().empty:
        delta = chart_df["Close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        chart_df["RSI_14"] = 100 - (100 / (1 + rs))

    # Configuración de estilo moderno y elegante
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    
    fig, (ax_main, ax_rsi) = plt.subplots(
        nrows=2,
        ncols=1,
        figsize=(11, 6.2),
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.12},
        dpi=300,
    )

    bg_color = "#ffffff"
    grid_color = "#f1f5f9"
    text_color = "#1e293b"
    fig.patch.set_facecolor(bg_color)
    ax_main.set_facecolor(bg_color)
    ax_rsi.set_facecolor(bg_color)

    # 1. PANEL PRINCIPAL: Precio y Medias
    dates = chart_df.index
    closes = chart_df["Close"].values

    # Línea de cierre principal con degradado sutil
    ax_main.plot(dates, closes, label=f"Cierre {ticker}", color="#0f172a", linewidth=1.8, zorder=4)
    ax_main.fill_between(dates, closes, min(closes) * 0.98, color="#3b82f6", alpha=0.04, zorder=2)

    # Medias Móviles
    if "SMA_50" in chart_df and not chart_df["SMA_50"].dropna().empty:
        ax_main.plot(dates, chart_df["SMA_50"], label="SMA 50 (Medio Plazo)", color="#f59e0b", linewidth=1.4, linestyle="--", alpha=0.9, zorder=3)

    if "SMA_200" in chart_df and not chart_df["SMA_200"].dropna().empty:
        ax_main.plot(dates, chart_df["SMA_200"], label="SMA 200 (Largo Plazo)", color="#8b5cf6", linewidth=1.5, alpha=0.9, zorder=3)

    # Niveles de Soportes y Resistencias
    current_p = technicals.current_close
    for s in technicals.key_supports[:2]:
        ax_main.axhline(y=s, color="#10b981", linestyle=":", linewidth=1.2, alpha=0.75, zorder=3)
        ax_main.text(dates[-1], s, f" Soporte ${s:.2f}", color="#059669", fontsize=8.5, fontweight="600", va="center")

    for r in technicals.key_resistances[:2]:
        ax_main.axhline(y=r, color="#ef4444", linestyle=":", linewidth=1.2, alpha=0.75, zorder=3)
        ax_main.text(dates[-1], r, f" Resistencia ${r:.2f}", color="#dc2626", fontsize=8.5, fontweight="600", va="center")

    # Formato de Panel Principal
    ax_main.set_title(f"{ticker} — Análisis Cuantitativo de Tendencia & Niveles Clave", fontsize=12, fontweight="bold", color=text_color, pad=10, loc="left")
    ax_main.legend(loc="upper left", frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0", fontsize=8.5)
    ax_main.tick_params(axis="both", colors="#64748b", labelsize=8.5)
    ax_main.grid(True, linestyle="--", alpha=0.7, color=grid_color)
    ax_main.set_ylabel("Cotización (USD)", fontsize=9, fontweight="600", color="#475569")
    ax_main.set_xlim(dates[0], dates[-1])

    # 2. PANEL INFERIOR: RSI (14) con mayor altura y etiquetas nítidas
    if "RSI_14" in chart_df and not chart_df["RSI_14"].dropna().empty:
        rsi_series = chart_df["RSI_14"]
        ax_rsi.plot(dates, rsi_series, color="#2563eb", linewidth=1.4, zorder=4)
        ax_rsi.axhline(y=70, color="#dc2626", linestyle="--", linewidth=1.2, alpha=0.85, zorder=2)
        ax_rsi.axhline(y=30, color="#16a34a", linestyle="--", linewidth=1.2, alpha=0.85, zorder=2)
        ax_rsi.axhline(y=50, color="#94a3b8", linestyle=":", linewidth=0.9, alpha=0.6, zorder=2)
        ax_rsi.fill_between(dates, rsi_series, 70, where=(rsi_series >= 70), color="#ef4444", alpha=0.2)
        ax_rsi.fill_between(dates, rsi_series, 30, where=(rsi_series <= 30), color="#10b981", alpha=0.2)
        ax_rsi.set_ylim(15, 85)
        ax_rsi.set_yticks([30, 50, 70])
        ax_rsi.set_yticklabels(["30", "50", "70"], fontsize=8.5, fontweight="600")

        # Etiquetas legibles de Sobrecompra (70) y Sobreventa (30)
        ax_rsi.text(
            dates[2],
            71.5,
            "Sobrecompra (70)",
            color="#b91c1c",
            fontsize=8.5,
            fontweight="700",
            va="bottom",
            zorder=5,
        )
        ax_rsi.text(
            dates[2],
            28.5,
            "Sobreventa (30)",
            color="#15803d",
            fontsize=8.5,
            fontweight="700",
            va="top",
            zorder=5,
        )
    
    ax_rsi.set_ylabel("RSI (14)", fontsize=8.5, fontweight="600", color="#475569")
    ax_rsi.tick_params(axis="both", colors="#64748b", labelsize=8)
    ax_rsi.grid(True, linestyle="--", alpha=0.7, color=grid_color)
    ax_rsi.set_xlim(dates[0], dates[-1])

    # Formato de fechas en el eje X
    ax_rsi.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax_rsi.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.setp(ax_main.get_xticklabels(), visible=False)

    fig.subplots_adjust(top=0.93, bottom=0.08, left=0.07, right=0.95)
    fig.savefig(
        dest_path,
        format="png",
        dpi=300,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    plt.close(fig)

    logger.info(f"Gráfico técnico guardado exitosamente: {dest_path}")
    return dest_path
