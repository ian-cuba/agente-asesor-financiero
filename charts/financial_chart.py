from __future__ import annotations
from pathlib import Path
import logging
from typing import Optional, List
import matplotlib.pyplot as plt
import numpy as np

from config import GENERATED_CHARTS_DIR
from data.schemas import AnnualFinancialRecord

logger = logging.getLogger(__name__)


def generate_financial_chart(
    records: List[AnnualFinancialRecord],
    ticker: str,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Genera un gráfico institucional de barras para la evolución histórica de
    Ingresos (Revenue) y Ganancia por Acción (EPS Diluido).
    """
    clean_ticker = ticker.upper()
    dest_path = output_path or (GENERATED_CHARTS_DIR / f"{clean_ticker}_financial.png")

    logger.info(f"Generando gráfico fundamental para {clean_ticker} en {dest_path}...")

    # Filtrar registros válidos
    valid_records = [r for r in records if r.revenue is not None or r.eps is not None]
    if not valid_records:
        logger.warning(f"No hay registros financieros suficientes para graficar {clean_ticker}")
        valid_records = records

    years = [r.year for r in valid_records]
    revenues_b = [(r.revenue / 1e9) if r.revenue is not None else 0.0 for r in valid_records]
    eps_vals = [r.eps if r.eps is not None else 0.0 for r in valid_records]

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    fig, ax1 = plt.subplots(figsize=(8.5, 4.2), dpi=300)

    bg_color = "#ffffff"
    grid_color = "#f1f5f9"
    fig.patch.set_facecolor(bg_color)
    ax1.set_facecolor(bg_color)

    x = np.arange(len(years))
    bar_width = 0.45

    # 1. Barras de Ingresos (Eje Y izquierdo)
    bars = ax1.bar(
        x,
        revenues_b,
        width=bar_width,
        color="#2563eb",
        alpha=0.88,
        label="Ingresos Totales (B USD)",
        zorder=3,
        edgecolor="#1d4ed8",
        linewidth=0.8,
    )

    # Etiquetas de valor encima de las barras de Revenue
    max_rev = max(revenues_b) if revenues_b else 10.0
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax1.annotate(
                f"${height:.1f}B",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="600",
                color="#1e3a8a",
            )

    ax1.set_ylabel("Ingresos Totales (Miles de Millones USD)", fontsize=9, fontweight="600", color="#1e3a8a")
    ax1.set_ylim(0, max_rev * 1.18)
    ax1.set_xticks(x)
    ax1.set_xticklabels(years, fontsize=9, fontweight="600", color="#1e293b")
    ax1.tick_params(axis="both", colors="#64748b", labelsize=8.5)
    ax1.grid(True, linestyle="--", alpha=0.7, color=grid_color)

    # 2. Línea de EPS Diluido (Eje Y derecho)
    ax2 = ax1.twinx()
    ax2.set_facecolor("none")
    ax2.grid(False)

    line = ax2.plot(
        x,
        eps_vals,
        color="#10b981",
        linewidth=2.2,
        marker="o",
        markersize=6,
        label="EPS Diluido (USD)",
        zorder=5,
    )

    # Etiquetas para EPS
    for i, txt in enumerate(eps_vals):
        ax2.annotate(
            f"${txt:.2f}",
            xy=(x[i], txt),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="700",
            color="#065f46",
        )

    min_eps = min(eps_vals) if eps_vals else 0
    max_eps = max(eps_vals) if eps_vals else 1.0
    eps_margin = (max_eps - min_eps) * 0.25 if max_eps != min_eps else 1.0
    ax2.set_ylim(min_eps - eps_margin, max_eps + eps_margin)
    ax2.set_ylabel("EPS Diluido (USD)", fontsize=9, fontweight="600", color="#065f46")
    ax2.tick_params(axis="y", colors="#065f46", labelsize=8.5)

    # Título y Leyendas combinadas
    plt.title(
        f"{clean_ticker} — Evolución Histórica de Facturación & Rentabilidad por Acción",
        fontsize=11,
        fontweight="bold",
        color="#0f172a",
        pad=12,
        loc="left",
    )

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines_1 + lines_2,
        labels_1 + labels_2,
        loc="upper left",
        frameon=True,
        facecolor="#ffffff",
        edgecolor="#e2e8f0",
        fontsize=8.5,
    )

    plt.tight_layout()
    fig.savefig(dest_path, format="png", dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    logger.info(f"Gráfico financiero guardado exitosamente: {dest_path}")
    return dest_path
