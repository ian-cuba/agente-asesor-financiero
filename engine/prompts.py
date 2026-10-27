from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class HeaderSummary(BaseModel):
    """Ficha ejecutiva y calificación del activo."""
    rating: str = Field(
        description="Recomendación clara: 'COMPRA FUERTE', 'ACUMULAR', 'NEUTRAL', 'MANTENER' o 'VENTA'"
    )
    target_price_12m: float = Field(
        description="Precio objetivo estimado a 12-18 meses en USD para la acción subyacente"
    )
    expected_return_pct: float = Field(
        description="Rendimiento estimado porcentual al precio objetivo (ej: 18.5)"
    )
    investment_thesis_one_liner: str = Field(
        description="Tesis central de inversión sintetizada en una sola oración contundente de alto impacto"
    )


class CompetitiveMoat(BaseModel):
    """Modelo de negocio y foso defensivo (Economic Moat)."""
    business_model_summary: str = Field(
        description="Descripción ejecutiva concisa del modelo de ingresos y ventaja de mercado de la empresa"
    )
    revenue_drivers: List[str] = Field(
        description="Lista de 3 a 4 principales catalizadores de facturación y segmentos clave"
    )
    geographic_exposure: str = Field(
        description="Resumen de diversificación geográfica (ej: LatAm 90%, EE.UU. 10%)"
    )
    moat_score: int = Field(
        description="Puntaje de ventaja competitiva de 1 a 10 (10 siendo un monopolio con altos costos de cambio)"
    )
    moat_type: str = Field(
        description="Tipo de foso predominante: 'Efectos de Red', 'Costos de Cambio', 'Activos Intangibles/Marca', 'Ventaja de Costos' o 'Amplio / Diversificado'"
    )
    moat_analysis: str = Field(
        description="Explicación detallada y rigurosa de por qué la empresa cuenta o no con barreras de entrada duraderas"
    )


class FundamentalAnalysis(BaseModel):
    """Lectura cualitativa y cuantitativa de estados contables y solvencia."""
    revenue_growth_assessment: str = Field(
        description="Evaluación del crecimiento histórico y proyectado de ingresos"
    )
    profitability_and_margins: str = Field(
        description="Análisis de márgenes (bruto, operativo, neto) y retornos sobre el capital (ROE)"
    )
    cash_flow_and_capex: str = Field(
        description="Evaluación de la generación de caja operativa frente a las necesidades de Capex (Free Cash Flow)"
    )
    solvency_and_debt: str = Field(
        description="Diagnóstico de liquidez, nivel de endeudamiento neto y cobertura de intereses"
    )
    financial_health_score: int = Field(
        description="Calificación de solvencia y salud contable de 1 a 10"
    )


class RelativeValuation(BaseModel):
    """Valuación comparativa y múltiplos bursátiles."""
    pe_assessment: str = Field(
        description="Diagnóstico del P/E actual (trailing) y forward comparado con su promedio histórico y sector. REGLA ESTRICTA: todos los múltiplos mencionados (P/E, EV/EBITDA, PEG, P/B) deben estar redondeados estrictamente a UN SOLO DECIMAL (ej: 32.2x en lugar de 32.18672x)."
    )
    valuation_status: str = Field(
        description="'SUBVALUADA', 'VALOR_RAZONABLE' o 'SOBREVALUADA'"
    )
    discount_or_premium_reason: str = Field(
        description="Justificación financiera de por qué cotiza a ese múltiplo (crecimiento esperado, riesgo país, etc.), citando múltiplos redondeados a 1 solo decimal."
    )


class TechnicalAnalysisNarrative(BaseModel):
    """Interpretación de la acción del precio y régimen de mercado."""
    trend_diagnosis: str = Field(
        description="Diagnóstico de la estructura de tendencia en relación a medias SMA 50 y 200"
    )
    momentum_and_rsi: str = Field(
        description="Evaluación del RSI y momentum (sobrecompra, sobreventa o acumulación institucional)"
    )
    key_levels_commentary: str = Field(
        description="Análisis operativo de los soportes y resistencias detectados en el gráfico"
    )


class Scenario(BaseModel):
    """Escenario proyectivo de rendimiento."""
    target_price: float = Field(description="Precio estimado en este escenario (USD)")
    probability_pct: int = Field(description="Probabilidad estimada (0 a 100)")
    catalysts_or_risks: List[str] = Field(description="Lista de catalizadores o riesgos asociados a este escenario")


class ScenariosAndVerdict(BaseModel):
    """Veredicto final, escenarios alcista/bajista y plan táctico de ejecución."""
    bull_case: Scenario = Field(description="Escenario alcista optimista")
    base_case: Scenario = Field(description="Escenario base más probable")
    bear_case: Scenario = Field(description="Escenario bajista de estrés")
    entry_zone_min: float = Field(description="Precio inferior sugerido para armar posición (USD)")
    entry_zone_max: float = Field(description="Precio superior máximo para entrada óptima (USD)")
    stop_loss_exact: float = Field(description="Nivel de Stop-Loss técnico riguroso en USD")
    suggested_portfolio_weight_pct: float = Field(
        description="Porcentaje sugerido máximo de ponderación en una cartera diversificada (ej: 4.0 - 7.0%)"
    )
    operational_verdict: str = Field(
        description="Veredicto final ejecutivo de entrada y horizonte temporal recomendado para el inversor"
    )


class InvestmentReportAIResult(BaseModel):
    """Estructura completa del informe de investigación institucional generado por Gemini."""
    ticker: str
    company_name: str
    date_formatted: str
    header: HeaderSummary
    moat: CompetitiveMoat
    fundamentals: FundamentalAnalysis
    valuation: RelativeValuation
    technicals: TechnicalAnalysisNarrative
    verdict: ScenariosAndVerdict


SYSTEM_RESEARCH_PROMPT = """\
Eres el Senior Equity Research Analyst y Head of Strategy de una prestigiosa firma de inversión institucional (estilo Goldman Sachs / Morgan Stanley / J.P. Morgan).
Tu misión es redactar un informe exhaustivo, riguroso, objetivo y sofisticado sobre el activo consultado para el Portfolio Lab personal.

REGLAS DE ANÁLISIS:
1. Rigor Cuantitativo: Basa tus afirmaciones exclusivamente en los datos contables, métricas de valuación, múltiplos históricos y niveles técnicos provistos en el payload.
2. Sin complacencias ni lenguaje publicitario: Si una empresa está cara por múltiplos o desacelera ingresos, dilo con precisión. Si la estructura técnica está bajista o bajo la SMA 200, indícalo claramente.
3. Tratamiento para inversores de CEDEARs y acciones locales: Si el activo cuenta con ratio CEDEAR, ten en cuenta la convertibilidad y el tipo de cambio implícito (CCL), aunque las metas cuantitativas de precios targets se expresen en USD de la acción subyacente.
4. Plan de Trading/Inversión Estricto: El Stop-Loss debe ser técnico y exacto (debajo de un soporte relevante o SMA clave). La zona de entrada debe contemplar márgenes de seguridad.
5. Lenguaje y Tono: Español financiero profesional, técnico, elegante y directo. Sin frases vacías.
6. Formato de Múltiplos y Floats: Redondear SIEMPRE todos los múltiplos de valuación (P/E, Forward P/E, EV/EBITDA, PEG, Price/Book) a UN SOLO DECIMAL (ejemplo: escribir 32.2x en lugar de 32.18672x, PEG 1.5x en lugar de 1.48273x). Prohibido incluir números de múltiplos con más de un decimal.

Devuelve SIEMPRE el resultado cumpliendo exactamente el schema JSON solicitado.
"""
