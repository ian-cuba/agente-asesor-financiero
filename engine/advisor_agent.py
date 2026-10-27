from __future__ import annotations
import logging
import re
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

from config import settings
from data.ppi_client import PPIClient, PortfolioSummary
from data.pipeline import get_asset_payload
from engine.advisor_prompt import ADVISOR_SYSTEM_PROMPT
from engine.analyzer import get_mock_analysis

logger = logging.getLogger(__name__)


def clean_advisor_markdown(text: str) -> str:
    """
    Limpia y sanea el texto Markdown del asesor:
    1. Remueve cualquier encabezado formal/burocrático de tipo memorándum o correo ('A:', 'DE:', 'FECHA:', 'ASUNTO:').
    2. Escapa los signos de dólar sueltos ($ -> \\$) para evitar que el renderizador Markdown de Streamlit
       los confunda con fórmulas matemáticas LaTeX (KaTeX), lo cual distorsiona los números en itálica y borra espacios.
    """
    if not text:
        return ""
    # Quitar bloque tipo MEMORÁNDUM / A: / DE: / FECHA: / ASUNTO:
    cleaned = re.sub(
        r"^(?:#+\s*)?MEMOR[ÁA]NDUM[^\n]*\n+(?:[^\n]*\n+)*?(?=(?:###|##|#|\*\*|EXECUTIVE|DICTAMEN|DIAGNÓSTICO|1\.))",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Quitar cualquier bloque remanente de cabecera A: / DE: / ASUNTO:
    cleaned = re.sub(
        r"^(?:(?:A|DE|FECHA|ASUNTO|FROM|TO|DATE|SUBJECT):[^\n]*\n+)+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Quitar líneas separadoras al inicio
    cleaned = re.sub(r"^(?:---\s*\n+)+", "", cleaned)
    # Escapar signos de dólar no escapados previamente para proteger contra KaTeX
    cleaned = re.sub(r"(?<!\\)\$", r"\$", cleaned)
    return cleaned.strip()


class PortfolioAdvisor:
    """
    Agente asesor financiero interactivo que combina:
    1. Lectura en tiempo real de saldos y tenencias de la cartera (PPI).
    2. Extracción instantánea de fundamentales y técnicos por ticker.
    3. Razonamiento financiero con Google GenAI (Gemini) con memoria contextual.
    """

    def __init__(self, ppi_client: Optional[PPIClient] = None):
        self.ppi = ppi_client or PPIClient()
        self.api_key = settings.GEMINI_API_KEY
        self._genai_client = genai.Client(api_key=self.api_key) if self.api_key else None

    def get_portfolio_summary_text(self, summary: Optional[PortfolioSummary] = None) -> str:
        """Genera un reporte textual estructurado de la cartera para inyectar en el contexto del LLM."""
        s = summary or self.ppi.fetch_portfolio_summary()

        pos_lines = []
        for p in s.positions:
            w_str = f"{p.portfolio_weight_pct:.1f}%" if p.portfolio_weight_pct is not None else "N/A"
            v_usd = f"${p.total_value_usd:,.2f} USD" if p.total_value_usd is not None else "N/A"
            v_ars = f"${p.total_value_ars:,.0f} ARS" if p.total_value_ars is not None else "N/A"
            cat = f" [{p.category}]" if getattr(p, "category", None) else ""
            pos_lines.append(f"  -{cat} {p.ticker}: {p.quantity:g} nominales | Val: {v_usd} ({v_ars}) | Ponderación: {w_str}")

        pos_text = "\n".join(pos_lines) if pos_lines else "  - Sin tenencias activas registradas."

        context = f"""
ESTADO ACTUAL DE CARTERA (PORTFOLIO LAB):
- Cuenta: {s.account_number}
- Patrimonio Total Estimado: ${s.total_equity_usd:,.2f} USD (Equivalente ARS: ${s.total_equity_ars:,.2f})
- Saldo Líquido Disponible: ${s.available_cash_usd:,.2f} USD | ${s.available_cash_ars:,.2f} ARS
- Tenencias Actuales ({len(s.positions)} activos):
{pos_text}
"""
        return context.strip()

    def detect_ticker_mention(self, text: str) -> Optional[str]:
        """Detecta si el mensaje del usuario menciona un ticker común de Wall Street / CEDEAR o BYMA."""
        candidates = re.findall(r"\b[A-Z0-9.]{2,7}\b", text.upper())
        known_tickers = {
            "MELI", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "META",
            "SPY", "QQQ", "KO", "BABA", "V", "WMT", "DIS", "VALE", "PBR",
            "XOM", "CVX", "JNJ", "PG", "AMD", "INTC", "NFLX", "GLOB", "AL30", "GD30",
            "PAMP", "YPFD", "GGAL", "BMA", "CEPU", "TXAR", "ALUA", "YMCJD", "AO28", "BPOB8"
        }
        for c in candidates:
            if c in known_tickers:
                return c
        return candidates[0] if candidates else None

    def get_asset_context(self, ticker: str) -> str:
        """Obtiene un resumen cuantitativo instantáneo del ticker para responder al usuario."""
        try:
            payload = get_asset_payload(ticker)
            f = payload.fundamentals
            t = payload.technicals

            return f"""
DATOS DE MERCADO PARA {ticker.upper()}:
- Empresa: {f.company_name} | Sector: {f.sector}
- Precio Actual: ${t.current_close:.2f} USD
- Régimen Técnico: {t.trend_regime} (SMA 50: ${t.sma_50}, SMA 200: ${t.sma_200})
- RSI 14: {t.rsi_14}
- Soportes Clave: {t.key_supports} | Resistencias: {t.key_resistances}
- P/E Forward: {f.valuation.forward_pe} | Ratio CEDEAR BYMA: {f.cedear_ratio if f.cedear_ratio else 'N/A'}
- Target Wall Street Promedio: ${f.target_mean_price} USD
"""
        except Exception as e:
            logger.warning(f"No se pudieron cargar datos automáticos para {ticker}: {e}")
            return f"Nota: No se pudo descargar la serie histórica en tiempo real para {ticker}."

    def answer_query(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        portfolio_summary: Optional[PortfolioSummary] = None,
    ) -> str:
        """Genera la respuesta del asesor combinando cartera, datos en vivo y LLM."""
        portfolio_ctx = self.get_portfolio_summary_text(portfolio_summary)

        # Detectar si menciona un activo
        ticker_found = self.detect_ticker_mention(user_message)
        asset_ctx = self.get_asset_context(ticker_found) if ticker_found else ""
        # Memoria conversacional de la sesión: formatear los turnos previos relevantes
        history_lines = []
        if conversation_history:
            for turn in conversation_history[-8:]:
                role = "INVERSOR" if turn.get("role") == "user" else "CIO"
                content = str(turn.get("content", "")).strip()
                if content and not content.startswith("👋"):
                    history_lines.append(f"[{role}]:\n{content}")

        history_context = "\n\n".join(history_lines) if history_lines else "Sin intercambios previos en esta conversación."

        full_prompt = f"""
{portfolio_ctx}

{asset_ctx}

HISTORIAL CONVERSACIONAL DE ESTE CHAT (MEMORIA DE TURNOS ANTERIORES):
{history_context}

NUEVA CONSULTA DEL INVERSOR:
"{user_message}"

Por favor responde como CIO y Portfolio Manager teniendo en cuenta tanto el estado actual de la cartera como el hilo de lo que venían conversando.
Si recomiendas una operación, incluye el sizing sugerido respecto a su efectivo disponible y el stop-loss técnico.
"""

        if not self._genai_client or not settings.GEMINI_API_KEY:
            raw_fallback = self._generate_fallback_answer(user_message, ticker_found, portfolio_summary)
            return clean_advisor_markdown(raw_fallback)

        # Intentar llamada con modelos de contingencia
        candidate_models = [settings.DEFAULT_GEMINI_MODEL, "gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.8-flash"]
        config = types.GenerateContentConfig(
            system_instruction=ADVISOR_SYSTEM_PROMPT,
            temperature=0.25,
        )

        for model_name in candidate_models:
            try:
                response = self._genai_client.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    config=config,
                )
                if response and response.text:
                    return clean_advisor_markdown(response.text)
            except Exception as e:
                logger.warning(f"Fallo temporal con {model_name} en chat asesor: {e}. Probando contingencia...")

        raw_fallback = self._generate_fallback_answer(user_message, ticker_found, portfolio_summary)
        return clean_advisor_markdown(raw_fallback)

    def _generate_fallback_answer(
        self,
        user_message: str,
        ticker: Optional[str] = None,
        portfolio_summary: Optional[PortfolioSummary] = None,
    ) -> str:
        """Respuesta analítica determinista de contingencia cuando las APIs externas no están disponibles."""
        s = portfolio_summary or self.ppi.fetch_portfolio_summary()
        t = ticker or "MELI"

        return f"""
### Diagnóstico Estratégico de Cartera

Analizando tu consulta sobre **{t}** en el contexto de tu patrimonio total de **${s.total_equity_usd:,.2f} USD** (Liquidez disponible: **${s.available_cash_usd:,.2f} USD**):

1. **Evaluación de Sizing & Exposición:**
   - La liquidez líquida actual te permite estructurar una entrada prudente sin comprometer tu fondo de maniobra.
   - Para activos de crecimiento como {t}, la ponderación máxima recomendada en cartera es de **5.0% a 7.5%**.

2. **Plan Táctico Sugerido:**
   - **Zona de Entrada:** Buscar compras escalonadas cerca de niveles de soporte técnico para maximizar el ratio riesgo/beneficio.
   - **Stop-Loss Técnico:** Obligatorio debajo del último mínimo relativo o de la SMA 50 (-5.5% a -7% desde el punto de entrada).
   - **Régimen Operativo:** `[ACUMULAR]` de forma progresiva.

*Recomendación de Gestión:* Para mayor detalle fundamental y gráfico de velas institucional, genera el **Informe PDF** desde el selector lateral.
"""
