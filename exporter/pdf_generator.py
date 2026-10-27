from __future__ import annotations
from pathlib import Path
import logging
from typing import Optional, Any, Dict
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

from config import TEMPLATES_DIR, REPORTS_DIR
from data.schemas import AssetPayload
from engine.prompts import InvestmentReportAIResult
from charts.technical_chart import generate_technical_chart
from charts.financial_chart import generate_financial_chart
from data.technical import fetch_technical_data

logger = logging.getLogger(__name__)


def build_html_report(
    payload: AssetPayload,
    analysis: InvestmentReportAIResult,
    technical_chart_path: Path,
    financial_chart_path: Path,
    output_html_path: Optional[Path] = None,
    cedear_details: Optional[dict] = None,
) -> Path:
    """Renderiza la plantilla Jinja2 del reporte y genera un archivo HTML autónomo de alta resolución."""
    ticker = payload.ticker.upper()
    dest_path = output_html_path or (REPORTS_DIR / f"{ticker}_research_report.html")

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("report_template.html")

    css_path = (TEMPLATES_DIR / "styles.css").resolve().as_uri()
    tech_uri = technical_chart_path.resolve().as_uri()
    fin_uri = financial_chart_path.resolve().as_uri()

    rendered_content = template.render(
        payload=payload,
        analysis=analysis,
        css_path=css_path,
        technical_chart_path=tech_uri,
        financial_chart_path=fin_uri,
        cedear=cedear_details or {},
    )

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(rendered_content)

    logger.info(f"Reporte HTML compilado exitosamente: {dest_path}")
    return dest_path


def render_to_pdf(html_path: Path, output_pdf_path: Optional[Path] = None) -> Path:
    """
    Compila el archivo HTML a un documento PDF de alta fidelidad utilizando Playwright en modo headless.
    Garantiza renderizado exacto de fuentes, gráficos, fondos y márgenes editoriales.
    """
    dest_pdf = output_pdf_path or html_path.with_suffix(".pdf")
    logger.info(f"Iniciando compilación PDF con Playwright headless para {html_path.name}...")

    html_uri = html_path.resolve().as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
        )
        page = browser.new_page()
        # Cargar documento local y esperar a que todas las fuentes e imágenes estén renderizadas
        page.goto(html_uri, wait_until="networkidle")

        page.pdf(
            path=str(dest_pdf),
            format="A4",
            print_background=True,
            margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
        )
        browser.close()

    logger.info(f"Documento PDF institucional generado con éxito mediante Playwright: {dest_pdf}")
    return dest_pdf


def generate_investment_report(
    payload: AssetPayload,
    analysis: InvestmentReportAIResult,
    raw_df: Optional[Any] = None,
    cedear_details: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Orquestador completo del reporte de inversión:
    1. Genera los gráficos técnicos y contables en alta definición.
    2. Renderiza la plantilla HTML Jinja2.
    3. Compila a PDF real mediante Playwright Chromium headless.
    """
    ticker = payload.ticker.upper()
    logger.info(f"Iniciando generación integral de reporte para {ticker}...")

    # 1. Obtener DataFrame técnico si no fue provisto
    if raw_df is None:
        df, _ = fetch_technical_data(ticker)
    else:
        df = raw_df

    # 2. Generar gráficos estáticos de alta definición
    tech_chart = generate_technical_chart(df, payload.technicals)
    fin_chart = generate_financial_chart(payload.fundamentals.financial_history, ticker)

    # 3. Renderizar documento HTML
    html_report = build_html_report(
        payload=payload,
        analysis=analysis,
        technical_chart_path=tech_chart,
        financial_chart_path=fin_chart,
        cedear_details=cedear_details,
    )

    # 4. Compilar directamente a PDF con Playwright
    pdf_report = render_to_pdf(html_report)
    return pdf_report
