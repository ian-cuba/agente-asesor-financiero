from __future__ import annotations
import argparse
import logging
import os
import sys
import webbrowser
from pathlib import Path

from config import settings, REPORTS_DIR
from data.pipeline import get_asset_payload
from data.ppi_client import PPIClient
from engine.analyzer import run_gemini_analysis, get_mock_analysis
from exporter.pdf_generator import generate_investment_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("InvestmentAgent")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Private Equity Research & Portfolio Lab — Pipeline Automatizado de Informes de Inversión"
    )
    parser.add_argument(
        "ticker",
        type=str,
        help="Ticker del activo (ej. MELI, AAPL, MSFT, NVDA, TSLA, SPY)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=settings.DEFAULT_GEMINI_MODEL,
        help=f"Modelo Gemini a utilizar (por defecto: {settings.DEFAULT_GEMINI_MODEL})",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Ejecuta en modo simulado/mock sin consumir tokens de la API de Google Gemini",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Abre el informe generado automáticamente en el visor predeterminado",
    )
    return parser.parse_args()


def run_pipeline(ticker: str, model_name: str, use_mock: bool = False, auto_open: bool = False) -> Path:
    clean_ticker = ticker.strip().upper()
    print("\n" + "=" * 70)
    print(f"  PRIVATE EQUITY RESEARCH & PORTFOLIO LAB — ANÁLISIS DE ACTIVO: {clean_ticker}")
    print("=" * 70)

    # 1. Extracción de Datos de Mercado y Fundamentales
    print(f"\n[1/5] Extrayendo estados contables y métricas técnicas para {clean_ticker}...")
    payload = get_asset_payload(clean_ticker)
    f = payload.fundamentals
    t = payload.technicals
    print(f"      • Compañía: {f.company_name} ({f.sector})")
    print(f"      • Precio de Cierre: ${t.current_close:.2f} USD")
    print(f"      • Régimen Técnico: {t.trend_regime} | RSI: {t.rsi_14}")
    if f.cedear_ratio:
        print(f"      • Ratio CEDEAR BYMA: {int(f.cedear_ratio)}:1")

    # 2. Conexión de Cartera PPI (Saldos y Sizing)
    print("\n[2/5] Consultando cartera en Portfolio Personal Inversiones (PPI)...")
    ppi = PPIClient()
    current_pos = ppi.get_ticker_position(clean_ticker)
    portfolio_ctx = ""
    if current_pos and current_pos.quantity > 0:
        portfolio_ctx = (
            f"El inversor posee actualmente {current_pos.quantity} títulos de {clean_ticker} "
            f"con una valuación de ${current_pos.total_value_usd:.2f} USD ({current_pos.portfolio_weight_pct}% de la cartera)."
        )
        print(f"      • Tenencia detectada: {current_pos.quantity} nominales (${current_pos.total_value_usd:.2f} USD)")
    else:
        portfolio_ctx = f"El inversor actualmente NO tiene posición abierta en {clean_ticker}."
        print("      • Sin posición previa registrada en cartera.")

    # 3. Motor de Análisis con LLM (Gemini con Structured Outputs)
    print(f"\n[3/5] Generando reporte cualitativo y cuantitativo...")
    if use_mock or not settings.GEMINI_API_KEY:
        if not settings.GEMINI_API_KEY:
            print("      • GEMINI_API_KEY no detectada en .env. Utilizando motor analítico estructurado de prueba.")
        else:
            print("      • Modo mock solicitado por el usuario.")
        analysis_result = get_mock_analysis(payload)
    else:
        print(f"      • Solicitando análisis a {model_name} con Structured Outputs (Pydantic)...")
        analysis_result = run_gemini_analysis(
            payload=payload,
            model_name=model_name,
            portfolio_context=portfolio_ctx,
        )

    # Sizing personalizado con PPI
    sizing = ppi.calculate_sizing_suggestion(
        ticker=clean_ticker,
        current_price_usd=t.current_close,
        suggested_weight_pct=analysis_result.verdict.suggested_portfolio_weight_pct,
        cedear_ratio=f.cedear_ratio,
    )
    print(f"      • Rating asignado: {analysis_result.header.rating}")
    print(f"      • Precio Objetivo 12M: ${analysis_result.header.target_price_12m:.2f} USD (+{analysis_result.header.expected_return_pct}%)")
    print(f"      • Sizing recomendado: {sizing['suggested_weight_pct']}% de cartera ({sizing['operational_action']})")
    if f.cedear_ratio:
        print(f"      • Cantidad sugerida en CEDEARs: ~{sizing['suggested_cedear_nominal_qty']} nominales")

    # 4. Generación de Gráficos y Renderizado Institucional con Playwright
    print("\n[4/5] Renderizando gráficos de alta resolución y compilando PDF nativo con Playwright...")
    report_doc = generate_investment_report(
        payload=payload,
        analysis=analysis_result,
        cedear_details=sizing,
    )

    # 5. Salida Final
    print("\n[5/5] ¡Documento PDF compilado con éxito!")
    print("-" * 70)
    print(f"Documento generado (PDF): {report_doc}")
    print(f"Enlace local: {report_doc.resolve().as_uri()}")
    print("-" * 70)

    if auto_open:
        print("Abriendo documento PDF...")
        webbrowser.open(report_doc.resolve().as_uri())

    return report_doc


def main():
    args = parse_arguments()
    try:
        run_pipeline(
            ticker=args.ticker,
            model_name=args.model,
            use_mock=args.mock,
            auto_open=args.open,
        )
    except Exception as e:
        logger.error(f"Error durante la ejecución del pipeline: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
