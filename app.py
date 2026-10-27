from __future__ import annotations
import os
import json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from config import settings, REPORTS_DIR, GENERATED_CHARTS_DIR
from data.pipeline import get_asset_payload
from data.chat_storage import (
    list_saved_chats,
    load_chat,
    save_chat,
    create_new_chat_session,
)
from engine.advisor_agent import PortfolioAdvisor, clean_advisor_markdown
from engine.analyzer import run_gemini_analysis, get_mock_analysis
from exporter.pdf_generator import generate_investment_report

# Configuración inicial de Streamlit
st.set_page_config(
    page_title="Portfolio Lab — Private Equity & Wealth Advisory",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilos CSS sutiles para pulir Streamlit al estándar institucional
st.markdown(
    """
    <style>
    /* Reducir espacio superior desperdiciado del sidebar */
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 1.1rem !important;
        padding-bottom: 1rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.5rem !important;
    }
    /* Tarjetas y métricas compactas compatibles con Dark Mode y Light Mode */
    [data-testid="stMetricValue"] {
        font-size: 1.15rem !important;
        font-weight: 700 !important;
        color: var(--text-color, inherit) !important;
        letter-spacing: -0.2px !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        color: var(--text-color, inherit) !important;
        opacity: 0.75 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.74rem !important;
        font-weight: 500 !important;
        opacity: 0.9 !important;
    }
    [data-testid="stMetric"] {
        background-color: var(--secondary-background-color, rgba(125, 125, 125, 0.08)) !important;
        border: 1px solid rgba(128, 128, 128, 0.2) !important;
        border-radius: 8px !important;
        padding: 8px 10px !important;
    }
    /* Selector de moneda minimalista y adaptable */
    div[data-testid="stRadio"] {
        margin: 0 !important;
        padding: 0 !important;
    }
    div[data-testid="stRadio"] > div {
        flex-direction: row !important;
        gap: 4px !important;
        align-items: center !important;
        margin-top: 2px !important;
    }
    div[data-testid="stRadio"] label {
        font-size: 0.75rem !important;
        font-weight: 700 !important;
        padding: 1px 6px !important;
        border-radius: 4px !important;
        cursor: pointer !important;
        color: var(--text-color, inherit) !important;
    }
    div[data-testid="stRadio"] label p {
        color: var(--text-color, inherit) !important;
    }
    .metric-card-container {
        background-color: var(--secondary-background-color, rgba(125, 125, 125, 0.08)) !important;
        border: 1px solid rgba(128, 128, 128, 0.2) !important;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    .badge-rating-buy {
        background-color: #059669;
        color: white;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 800;
        display: inline-block;
    }
    .badge-rating-acc {
        background-color: #7c3aed;
        color: white;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 800;
        display: inline-block;
    }
    .stDownloadButton button {
        background-color: #0284c7 !important;
        color: white !important;
        font-weight: 700 !important;
        border-radius: 6px !important;
        width: 100%;
    }
    /* Estilos para selectbox de sesiones y chips de consultas */
    div[data-testid="stSelectbox"] {
        min-width: 200px;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] {
        border-radius: 8px !important;
    }
    /* Separación armónica entre la columna del selector y el botón Nuevo */
    div[data-testid="column"]:has(div[data-testid="stSelectbox"]) {
        padding-right: 0.75rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# CONTROL DE AUTENTICACIÓN / ACCESO
# -----------------------------------------------------------------------------
def check_authentication() -> bool:
    """Verifica si el usuario está autenticado si existe contraseña configurada."""
    # Obtener contraseña desde st.secrets o settings (.env)
    configured_pwd = None
    try:
        configured_pwd = st.secrets.get("APP_PASSWORD") or st.secrets.get("PASSWORD")
    except Exception:
        pass
    
    if not configured_pwd:
        configured_pwd = getattr(settings, "APP_PASSWORD", None)

    # Si no hay contraseña configurada en secrets ni .env, se asume libre (entorno local dev)
    if not configured_pwd:
        return True

    if st.session_state.get("authenticated", False):
        return True

    # Renderizar pantalla de inicio de sesión centrada y estilizada
    _, col_center, _ = st.columns([1, 1.4, 1])
    with col_center:
        st.markdown("<div style='height: 4vh;'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style="text-align: center; margin-bottom: 1.5rem;">
                <span style="font-size: 2.5rem;">🔒</span>
                <h2 style="margin: 0.2rem 0; font-weight: 700;">Portfolio Lab</h2>
                <p style="color: gray; font-size: 0.9rem;">Acceso privado y confidencial</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            entered_pwd = st.text_input("Contraseña de acceso", type="password", placeholder="••••••••")
            submit_btn = st.form_submit_button("Ingresar", use_container_width=True)

            if submit_btn:
                if entered_pwd == configured_pwd:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta. Verifícala e intenta nuevamente.")

    return False


if not check_authentication():
    st.stop()

# -----------------------------------------------------------------------------
# GESTIÓN DE ESTADO (SESSION STATE)
# -----------------------------------------------------------------------------
if "current_chat_id" not in st.session_state:
    saved = list_saved_chats()
    if saved:
        first_chat = load_chat(saved[0]["id"])
        if first_chat:
            st.session_state.current_chat_id = first_chat["id"]
            st.session_state.current_chat_title = first_chat.get("title", "Conversación de Cartera")
            st.session_state.messages = first_chat.get("messages", [])
        else:
            new_s = create_new_chat_session()
            st.session_state.current_chat_id = new_s["id"]
            st.session_state.current_chat_title = new_s["title"]
            st.session_state.messages = new_s["messages"]
            save_chat(new_s["id"], new_s["title"], new_s["messages"], new_s["created_at"])
    else:
        new_s = create_new_chat_session()
        st.session_state.current_chat_id = new_s["id"]
        st.session_state.current_chat_title = new_s["title"]
        st.session_state.messages = new_s["messages"]
        save_chat(new_s["id"], new_s["title"], new_s["messages"], new_s["created_at"])

if "messages" not in st.session_state:
    st.session_state.messages = []

if "advisor" not in st.session_state:
    st.session_state.advisor = PortfolioAdvisor()

if "portfolio" not in st.session_state:
    st.session_state.portfolio = st.session_state.advisor.ppi.fetch_portfolio_summary()

if "current_payload" not in st.session_state:
    st.session_state.current_payload = None

if "current_analysis" not in st.session_state:
    st.session_state.current_analysis = None

if "last_pdf_path" not in st.session_state:
    st.session_state.last_pdf_path = None


# -----------------------------------------------------------------------------
# SIDEBAR: RESUMEN DE CARTERA & ACCIONES RÁPIDAS
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
            <span style="font-size:1.15rem; font-weight:800; color:var(--text-color, inherit); letter-spacing:-0.3px;">🏛️ Portfolio Lab</span>
            <span style="font-size:0.65rem; font-weight:700; color:var(--text-color, inherit); opacity:0.75; background:rgba(128,128,128,0.18); padding:2px 6px; border-radius:4px; text-transform:uppercase;">Advisory</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    p = st.session_state.portfolio
    ppi_client = st.session_state.advisor.ppi
    is_demo = getattr(ppi_client, "is_demo_mode", False)

    if "selected_currency" not in st.session_state:
        st.session_state.selected_currency = "ARS"

    # Fila única y ultra-compacta: [Cuenta #270090] [ARS | USD] [↻]
    col_acc, col_curr, col_btn = st.columns([1.3, 1.6, 0.45])
    with col_acc:
        if is_demo:
            st.markdown(
                """
                <div style="display:flex; align-items:center; gap:5px; padding-top:6px;">
                    <span style="height:7px; width:7px; background-color:#eab308; border-radius:50%; display:inline-block;"></span>
                    <span style="font-size:0.75rem; font-weight:700; color:#eab308;">Demo</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div style="display:flex; align-items:center; gap:5px; padding-top:6px;">
                    <span style="height:7px; width:7px; background-color:#10b981; border-radius:50%; display:inline-block; box-shadow:0 0 5px rgba(16,185,129,0.8);"></span>
                    <span style="font-size:0.78rem; font-weight:700; color:var(--text-color, inherit); font-family:monospace;">#{p.account_number}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with col_curr:
        chosen_curr = st.radio(
            "Moneda",
            options=["ARS", "USD"],
            index=0 if st.session_state.selected_currency == "ARS" else 1,
            horizontal=True,
            label_visibility="collapsed",
            key="currency_mode_selector",
        )
        st.session_state.selected_currency = chosen_curr
    with col_btn:
        if st.button("↻", help="Sincronizar saldos y posiciones con PPI", width="stretch"):
            with st.spinner("..."):
                st.session_state.advisor.ppi._cached_summary = None
                st.session_state.portfolio = st.session_state.advisor.ppi.fetch_portfolio_summary()
                st.toast("Cartera sincronizada con éxito.", icon="✅")
                st.rerun()

    # Si está en modo demo, mostrar guía informativa colapsable
    if is_demo:
        with st.expander("ℹ️ ¿Por qué veo datos de prueba?"):
            if getattr(ppi_client, "last_error", None):
                st.error(ppi_client.last_error)
            st.markdown(
                """
                Para conectar tu **cartera real de PPI**, verifica en tu `.env`:
                1. `PPI_CLIENT_KEY`: Tu Client Key provisto por PPI.
                2. `PPI_ACCOUNT_NUMBER`: Tu número de comitente (ej: `270090`).
                3. `PPI_API_KEY` y `PPI_API_SECRET`.
                """
            )

    # Métricas de Liquidez y Patrimonio con selección de moneda y tipografía moderada
    show_ars = (st.session_state.selected_currency == "ARS")
    if show_ars:
        eq_main = f"${p.total_equity_ars:,.0f} ARS"
        eq_sub = f"≈ ${p.total_equity_usd:,.2f} USD"
        cash_main = f"${p.available_cash_ars:,.0f} ARS"
        cash_sub = f"≈ ${p.available_cash_usd:,.2f} USD"
    else:
        eq_main = f"${p.total_equity_usd:,.2f} USD"
        eq_sub = f"≈ ${p.total_equity_ars:,.0f} ARS"
        cash_main = f"${p.available_cash_usd:,.2f} USD"
        cash_sub = f"≈ ${p.available_cash_ars:,.0f} ARS"

    m1, m2 = st.columns(2)
    with m1:
        st.metric(
            label="Patrimonio Total",
            value=eq_main,
            delta=eq_sub,
        )
    with m2:
        st.metric(
            label="Efectivo Disponible",
            value=cash_main,
            delta=cash_sub,
        )

    # Tabla de Posiciones Actuales
    st.markdown("#### 💼 Tenencias en Cartera")
    if p.positions:
        pos_data = []
        for pos in p.positions:
            qty_str = f"{pos.quantity:,.2f}".rstrip('0').rstrip('.') if (pos.quantity % 1 != 0) else f"{int(pos.quantity):,}"
            row = {
                "Ticker": pos.ticker,
                "Tipo": getattr(pos, "category", "") or "ACTIVO",
                "Nominales": qty_str,
            }
            if show_ars:
                row["Valor ($)"] = f"${pos.total_value_ars:,.0f}" if pos.total_value_ars is not None else "-"
                row["Valor (US$)"] = f"${pos.total_value_usd:,.2f}" if pos.total_value_usd is not None else "-"
            else:
                row["Valor (US$)"] = f"${pos.total_value_usd:,.2f}" if pos.total_value_usd is not None else "-"
                row["Valor ($)"] = f"${pos.total_value_ars:,.0f}" if pos.total_value_ars is not None else "-"

            row["% Cartera"] = f"{pos.portfolio_weight_pct:.1f}%" if pos.portfolio_weight_pct is not None else "-"
            pos_data.append(row)

        st.dataframe(
            pd.DataFrame(pos_data),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("Sin tenencias registradas en la cartera.")

    st.markdown("---")
    col_ticker, col_action = st.columns([1.1, 1.3], vertical_alignment="bottom")
    with col_ticker:
        ticker_input = st.text_input(
            "Ticker:",
            value="MELI",
            placeholder="Ej: AAPL",
            help="Ingresa el ticker (NYSE/NASDAQ/BYMA)",
        ).strip().upper()
    with col_action:
        btn_pdf = st.button("📄 Analizar y Generar PDF", width="stretch")

    # Estado de credenciales
    st.markdown("---")
    gemini_status = "🟢 Conectado" if settings.GEMINI_API_KEY else "🟡 Modo Mock"
    ppi_status = "🟢 En Línea" if st.session_state.advisor.ppi.is_configured else "⚪ Demo"
    st.caption(f"Motor LLM: **{gemini_status}** | Broker: **{ppi_status}**")

    # Botón de Cerrar Sesión si hay contraseña configurada
    if st.session_state.get("authenticated", False):
        if st.button("🔒 Cerrar Sesión", width="stretch", help="Cerrar la sesión actual"):
            st.session_state.authenticated = False
            st.rerun()


# -----------------------------------------------------------------------------
# EJECUCIÓN DE ACCIONES DESDE SIDEBAR
# -----------------------------------------------------------------------------
if btn_pdf:
    with st.spinner(f"Procesando métricas de mercado para {ticker_input}..."):
        try:
            # 1. Extracción cuantitativa
            payload = get_asset_payload(ticker_input)
            st.session_state.current_payload = payload

            # 2. Análisis LLM
            if settings.GEMINI_API_KEY:
                analysis = run_gemini_analysis(payload)
            else:
                analysis = get_mock_analysis(payload)
            st.session_state.current_analysis = analysis

            # 3. Compilación PDF
            with st.spinner(f"Compilando informe PDF nativo con Playwright para {ticker_input}..."):
                sizing = st.session_state.advisor.ppi.calculate_sizing_suggestion(
                    ticker=ticker_input,
                    current_price_usd=payload.technicals.current_close,
                    suggested_weight_pct=analysis.verdict.suggested_portfolio_weight_pct,
                    cedear_ratio=payload.fundamentals.cedear_ratio,
                )
                pdf_path = generate_investment_report(
                    payload=payload,
                    analysis=analysis,
                    cedear_details=sizing,
                )
                st.session_state.last_pdf_path = pdf_path
                st.toast(f"Informe PDF de {ticker_input} generado con éxito.", icon="📄")

            st.toast(f"Activo {ticker_input} analizado exitosamente.", icon="📈")
        except Exception as e:
            st.error(f"Error procesando el activo {ticker_input}: {e}")


# -----------------------------------------------------------------------------
# ÁREA PRINCIPAL: PESTAÑAS INTERACTIVAS
# -----------------------------------------------------------------------------
tab_chat, tab_reports = st.tabs(["💬 Chat Asesor de Cartera", "📑 Visor de Informes & Research"])

# =============================================================================
# PESTAÑA 1: CHAT ASESOR DE CARTERA
# =============================================================================
with tab_chat:
    # Selector de Historial de Chats y Creación de Nuevos Chats
    saved_chats = list_saved_chats()
    # Mapeo de ID a título completo y versión corta formateada
    chat_full_titles = {c["id"]: c.get("title", "Conversación") for c in saved_chats}
    chat_display_options = {
        c["id"]: f"{c.get('updated_at', '')[:16]} — {(c.get('title', 'Conversación')[:26] + '...') if len(c.get('title', 'Conversación')) > 26 else c.get('title', 'Conversación')}"
        for c in saved_chats
    }
    if st.session_state.current_chat_id not in chat_display_options:
        curr_t = st.session_state.get("current_chat_title", "Conversación")
        chat_full_titles[st.session_state.current_chat_id] = curr_t
        chat_display_options[st.session_state.current_chat_id] = f"Actual — {(curr_t[:26] + '...') if len(curr_t) > 26 else curr_t}"

    active_full_title = chat_full_titles.get(st.session_state.current_chat_id, "Conversación activa")

    top_chat_col1, top_chat_col2, top_chat_col3 = st.columns([2.3, 1.4, 0.75])
    with top_chat_col1:
        st.markdown("### 🤖 Asesor Financiero & CIO Personal")
        st.caption("Consultas estratégicas en tiempo real con memoria y contexto de tus saldos.")

    with top_chat_col2:
        keys_list = list(chat_display_options.keys())
        current_idx = keys_list.index(st.session_state.current_chat_id) if st.session_state.current_chat_id in keys_list else 0
        selected_chat_id = st.selectbox(
            "Historial de Sesiones",
            options=keys_list,
            index=current_idx,
            format_func=lambda cid: chat_display_options.get(str(cid), str(cid)),
            label_visibility="collapsed",
            help=f"Tema del chat activo:\n\"{active_full_title}\"",
        )
        if selected_chat_id and selected_chat_id != st.session_state.current_chat_id:
            chat_data = load_chat(str(selected_chat_id))
            if chat_data:
                st.session_state.current_chat_id = str(selected_chat_id)
                st.session_state.current_chat_title = chat_data.get("title", "Conversación")
                st.session_state.messages = chat_data.get("messages", [])
                st.rerun()

    with top_chat_col3:
        if st.button("+ Nuevo", width="stretch", help="Iniciar una nueva sesión de consulta limpia"):
            new_s = create_new_chat_session()
            st.session_state.current_chat_id = new_s["id"]
            st.session_state.current_chat_title = new_s["title"]
            st.session_state.messages = new_s["messages"]
            save_chat(new_s["id"], new_s["title"], new_s["messages"], new_s["created_at"])
            st.rerun()

    # Inyección de atributos title HTML en las opciones del desplegable para que al hacer hover se lea completo
    titles_json = json.dumps(chat_full_titles)
    tooltip_script = f"""
    <script>
        function setSelectOptionsTitle() {{
            try {{
                const titles = {titles_json};
                const doc = window.parent.document;
                // Buscar opciones en menú flotante y dropdowns de BaseWeb
                const optionElements = doc.querySelectorAll('li[role="option"], div[role="option"], ul[role="listbox"] li');
                optionElements.forEach((el, index) => {{
                    const txt = (el.innerText || el.textContent || '').trim();
                    let matched = false;
                    for (const [cid, fullTitle] of Object.entries(titles)) {{
                        const cleanT = fullTitle.trim();
                        // Match por fragmento inicial o subcadena
                        if (txt.includes(cleanT.slice(0, 14)) || cleanT.includes(txt.slice(18).replace(/\\.\\.\\.$/, '')) || (txt.startsWith(cleanT.slice(0, 8)))) {{
                            el.setAttribute('title', cleanT);
                            el.querySelectorAll('*').forEach(c => c.setAttribute('title', cleanT));
                            matched = true;
                            break;
                        }}
                    }}
                }});
            }} catch (e) {{}}
        }}
        const parentDoc = window.parent.document;
        parentDoc.addEventListener('mouseover', setSelectOptionsTitle, true);
        setInterval(setSelectOptionsTitle, 350);
    </script>
    """
    components.html(tooltip_script, height=0)

    # -------------------------------------------------------------------------
    # SUGERENCIAS INTELIGENTES DINÁMICAS (MACRO + ACTIVOS REALES EN CARTERA)
    # -------------------------------------------------------------------------
    p_positions = st.session_state.portfolio.positions if (st.session_state.portfolio and st.session_state.portfolio.positions) else []
    # Filtrar activos excluyendo FCI de liquidez inmediata
    user_tickers = [pos.ticker for pos in p_positions if not any(term in pos.ticker.upper() for term in ["FCI", "LIQ", "PESOS", "NOV.LIQ"])]

    # Seleccionar activo principal (mayor ponderación o primer activo relevante)
    primary_ticker = user_tickers[0] if user_tickers else "MELI"
    secondary_ticker = user_tickers[1] if len(user_tickers) > 1 else ("SPY" if "SPY" not in user_tickers else "YPFD")

    # Definir chips adaptados a su cartera real y coyuntura macro (tasa/inflación/brecha)
    chip_1_label = f"⚖️ Rebalancear cartera ({primary_ticker})"
    chip_1_prompt = f"¿Cómo sugieres rebalancear mi cartera hoy considerando mi posición en {primary_ticker}, mi efectivo disponible y el contexto macroeconómico?"

    chip_2_label = f"📈 Diagnóstico táctico de {primary_ticker}"
    chip_2_prompt = f"Realiza un diagnóstico de valuación, timing y riesgo de mi posición en {primary_ticker}. ¿Conviene sumar nominales, tomar ganancias o esperar?"

    chip_3_label = f"🇦🇷 Cobertura cambiaria y tasa real ({secondary_ticker})"
    chip_3_prompt = f"Ante la coyuntura macro de tasas, inflación y tipo de cambio en Argentina, ¿cómo ves mi exposición en renta fija vs CEDEARs ({secondary_ticker})? ¿Recomiendas alguna rotación?"

    col_chip1, col_chip2, col_chip3 = st.columns(3)
    with col_chip1:
        if st.button(chip_1_label, width="stretch", help=chip_1_prompt):
            st.session_state.messages.append({"role": "user", "content": chip_1_prompt})
            with st.spinner("Analizando estructura de cartera y contexto..."):
                ans = st.session_state.advisor.answer_query(
                    user_message=chip_1_prompt,
                    conversation_history=st.session_state.messages,
                    portfolio_summary=st.session_state.portfolio,
                )
                st.session_state.messages.append({"role": "assistant", "content": ans})
                if st.session_state.current_chat_title.startswith("Conversación"):
                    st.session_state.current_chat_title = f"Rebalanceo de {primary_ticker}"
                save_chat(st.session_state.current_chat_id, st.session_state.current_chat_title, st.session_state.messages)
            st.rerun()

    with col_chip2:
        if st.button(chip_2_label, width="stretch", help=chip_2_prompt):
            st.session_state.messages.append({"role": "user", "content": chip_2_prompt})
            with st.spinner(f"Evaluando métricas tácticas para {primary_ticker}..."):
                ans = st.session_state.advisor.answer_query(
                    user_message=chip_2_prompt,
                    conversation_history=st.session_state.messages,
                    portfolio_summary=st.session_state.portfolio,
                )
                st.session_state.messages.append({"role": "assistant", "content": ans})
                if st.session_state.current_chat_title.startswith("Conversación"):
                    st.session_state.current_chat_title = f"Diagnóstico {primary_ticker}"
                save_chat(st.session_state.current_chat_id, st.session_state.current_chat_title, st.session_state.messages)
            st.rerun()

    with col_chip3:
        if st.button(chip_3_label, width="stretch", help=chip_3_prompt):
            st.session_state.messages.append({"role": "user", "content": chip_3_prompt})
            with st.spinner("Evaluando macro y estrategia cambiaria..."):
                ans = st.session_state.advisor.answer_query(
                    user_message=chip_3_prompt,
                    conversation_history=st.session_state.messages,
                    portfolio_summary=st.session_state.portfolio,
                )
                st.session_state.messages.append({"role": "assistant", "content": ans})
                if st.session_state.current_chat_title.startswith("Conversación"):
                    st.session_state.current_chat_title = "Macro & Cobertura"
                save_chat(st.session_state.current_chat_id, st.session_state.current_chat_title, st.session_state.messages)
            st.rerun()

    st.markdown("---")

    # Mostrar historial de conversación
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            content = clean_advisor_markdown(msg["content"]) if msg["role"] == "assistant" else msg["content"]
            st.markdown(content)

    # Componente invisible para auto-scroll y botón flotante para scroll rápido hacia arriba
    components.html(
        """
        <script>
            function scrollToBottom() {
                try {
                    const doc = window.parent.document;
                    const mainSec = doc.querySelector('section.main') || doc.documentElement;
                    if (mainSec) {
                        mainSec.scrollTo({
                            top: mainSec.scrollHeight,
                            behavior: 'smooth'
                        });
                    }
                } catch (e) {}
            }
            scrollToBottom();
            setTimeout(scrollToBottom, 250);

            // Inyectar botón flotante 'Scroll to Top' fijo abajo a la derecha
            function injectScrollTopBtn() {
                try {
                    const topDoc = (window.top && window.top.document) ? window.top.document : (window.parent.document || document);
                    const topWin = (window.top) ? window.top : window.parent;

                    let btn = topDoc.getElementById('btn-scroll-top-cio');
                    if (!btn) {
                        btn = topDoc.createElement('button');
                        btn.id = 'btn-scroll-top-cio';
                        btn.innerHTML = '▲';
                        btn.setAttribute('title', 'Volver arriba rápidamente');
                        btn.setAttribute('aria-label', 'Volver arriba');

                        btn.style.cssText = `
                            position: fixed !important;
                            bottom: 28px !important;
                            right: 28px !important;
                            width: 42px !important;
                            height: 42px !important;
                            border-radius: 50% !important;
                            background-color: #0f172a !important;
                            color: #38bdf8 !important;
                            border: 2px solid #38bdf8 !important;
                            box-shadow: 0 4px 18px rgba(0, 0, 0, 0.6) !important;
                            cursor: pointer !important;
                            font-size: 19px !important;
                            font-weight: 900 !important;
                            display: flex !important;
                            align-items: center !important;
                            justify-content: center !important;
                            z-index: 9999999 !important;
                            transition: all 0.25s ease !important;
                            outline: none !important;
                            opacity: 0.95 !important;
                        `;

                        btn.addEventListener('mouseenter', () => {
                            btn.style.transform = 'translateY(-3px) scale(1.1)';
                            btn.style.backgroundColor = '#0284c7';
                            btn.style.color = '#ffffff';
                            btn.style.borderColor = '#ffffff';
                        });

                        btn.addEventListener('mouseleave', () => {
                            btn.style.transform = 'none';
                            btn.style.backgroundColor = '#0f172a';
                            btn.style.color = '#38bdf8';
                            btn.style.borderColor = '#38bdf8';
                        });

                        btn.addEventListener('click', () => {
                            const mainSec = topDoc.querySelector('section.main') || topDoc.querySelector('[data-testid="stMain"]');
                            if (mainSec && mainSec.scrollTop > 0) {
                                mainSec.scrollTo({ top: 0, behavior: 'smooth' });
                            }
                            topWin.scrollTo({ top: 0, behavior: 'smooth' });
                            topDoc.documentElement.scrollTo({ top: 0, behavior: 'smooth' });
                            topDoc.body.scrollTo({ top: 0, behavior: 'smooth' });
                        });

                        topDoc.body.appendChild(btn);
                    }

                    // Función para determinar si hay scroll
                    function checkScroll() {
                        const mainSec = topDoc.querySelector('section.main') || topDoc.querySelector('[data-testid="stMain"]');
                        const mainScroll = mainSec ? mainSec.scrollTop : 0;
                        const winScroll = topWin.pageYOffset || topWin.scrollY || topDoc.documentElement.scrollTop || topDoc.body.scrollTop || 0;
                        const currentScroll = Math.max(mainScroll, winScroll);

                        if (currentScroll > 150) {
                            btn.style.display = 'flex';
                            btn.style.opacity = '1';
                            btn.style.pointerEvents = 'auto';
                        } else {
                            btn.style.display = 'none';
                            btn.style.opacity = '0';
                            btn.style.pointerEvents = 'none';
                        }
                    }

                    const mainSec = topDoc.querySelector('section.main') || topDoc.querySelector('[data-testid="stMain"]');
                    if (mainSec) mainSec.addEventListener('scroll', checkScroll, { passive: true });
                    topWin.addEventListener('scroll', checkScroll, { passive: true });
                    topDoc.addEventListener('scroll', checkScroll, { passive: true });
                    setInterval(checkScroll, 400);
                    checkScroll();

                } catch (e) {}
            }
            injectScrollTopBtn();
            setTimeout(injectScrollTopBtn, 300);
            setTimeout(injectScrollTopBtn, 1000);
        </script>
        """,
        height=0,
    )

    # Entrada de texto del usuario
    if prompt := st.chat_input("Escribe tu consulta sobre inversión, sizing de CEDEARs o rotaciones..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("El CIO está evaluando tu consulta..."):
                response_text = st.session_state.advisor.answer_query(
                    user_message=prompt,
                    conversation_history=st.session_state.messages,
                    portfolio_summary=st.session_state.portfolio,
                )
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})

                # Si es el primer mensaje del usuario, derivar un título representativo
                if len(st.session_state.messages) <= 3 and (
                    st.session_state.current_chat_title.startswith("Conversación")
                    or st.session_state.current_chat_title.startswith("Nueva")
                ):
                    clean_title = prompt.strip().capitalize()
                    st.session_state.current_chat_title = (clean_title[:32] + "...") if len(clean_title) > 32 else clean_title

                # Persistir sesión en disco
                save_chat(
                    chat_id=st.session_state.current_chat_id,
                    title=st.session_state.current_chat_title,
                    messages=st.session_state.messages,
                )
        st.rerun()


# =============================================================================
# PESTAÑA 2: VISOR DE INFORMES & RESEARCH
# =============================================================================
with tab_reports:
    st.markdown("### 📑 Terminal de Research Institucional")
    st.caption("Informes cuantitativos, visualización de gráficos y descarga de PDFs de alta resolución.")

    payload = st.session_state.current_payload
    analysis = st.session_state.current_analysis

    if payload and analysis:
        f = payload.fundamentals
        t = payload.technicals

        # Encabezado del Activo
        col_hdr1, col_hdr2 = st.columns([3, 1])
        with col_hdr1:
            st.subheader(f"{f.company_name} ({f.ticker})")
            st.write(
                f"**Sector:** {f.sector} | **Industria:** {f.industry} | "
                f"**Ratio CEDEAR:** {f.cedear_ratio if f.cedear_ratio else 'Acción directa'}"
            )
            st.info(f"💡 *Tesis Central:* {analysis.header.investment_thesis_one_liner}")

        with col_hdr2:
            rating_style = "badge-rating-buy" if "COMPRA" in analysis.header.rating else "badge-rating-acc"
            st.markdown(
                f"<div style='text-align: right;'><span class='{rating_style}'>{analysis.header.rating}</span></div>",
                unsafe_allow_html=True,
            )
            st.metric(
                label="Precio Objetivo 12M",
                value=f"${analysis.header.target_price_12m:.2f} USD",
                delta=f"+{analysis.header.expected_return_pct:.1f}% Upside",
            )

        # Fila de Métricas Clave
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Precio Cierre", f"${t.current_close:.2f}")
        k2.metric("Market Cap", f"${f.valuation.market_cap / 1e9:.1f}B" if f.valuation.market_cap else "N/A")
        k3.metric("P/E Forward", f"{f.valuation.forward_pe:.1f}x" if f.valuation.forward_pe else "N/A")
        k4.metric("Moat Score", f"{analysis.moat.moat_score}/10")
        k5.metric("RSI (14D)", f"{t.rsi_14:.1f}" if t.rsi_14 else "N/A")
        k6.metric("Salud Contable", f"{analysis.fundamentals.financial_health_score}/10")

        # Tarjeta de Comando Táctico
        st.markdown("#### ⚡ Cockpit Táctico de Ejecución")
        cmd_c1, cmd_c2, cmd_c3, cmd_c4 = st.columns(4)
        cmd_c1.metric("Zona Óptima de Entrada", f"${analysis.verdict.entry_zone_min:.2f} - ${analysis.verdict.entry_zone_max:.2f}")
        cmd_c2.metric("Stop-Loss Técnico Exacto", f"${analysis.verdict.stop_loss_exact:.2f}")
        cmd_c3.metric("Sizing Sugerido", f"{analysis.verdict.suggested_portfolio_weight_pct:.1f}%")
        
        downside = t.current_close - analysis.verdict.stop_loss_exact
        upside = analysis.header.target_price_12m - t.current_close
        rr_ratio = f"1 : {upside / downside:.1f}" if downside > 0 and upside > 0 else "Favorable"
        cmd_c4.metric("Riesgo / Beneficio", rr_ratio)

        st.success(f"**Veredicto Operativo:** {analysis.verdict.operational_verdict}")

        # Gráficos incrustados
        st.markdown("#### 📊 Visualizaciones Cuantitativas Generadas")
        g1, g2 = st.columns(2)

        tech_img = GENERATED_CHARTS_DIR / f"{f.ticker}_technical.png"
        fin_img = GENERATED_CHARTS_DIR / f"{f.ticker}_financial.png"

        with g1:
            if tech_img.exists():
                st.image(str(tech_img), caption=f"Estructura Técnica y Medias Móviles de {f.ticker}", width="stretch")
            else:
                st.info("Gráfico técnico pendiente de generación.")

        with g2:
            if fin_img.exists():
                st.image(str(fin_img), caption=f"Evolución de Ingresos y Ganancia por Acción (EPS) de {f.ticker}", width="stretch")
            else:
                st.info("Gráfico contable pendiente de generación.")

        # Descarga de PDF
        st.markdown("---")
        pdf_file = st.session_state.last_pdf_path or (REPORTS_DIR / f"{f.ticker}_research_report.pdf")
        if pdf_file and Path(pdf_file).exists():
            with open(pdf_file, "rb") as f_pdf:
                st.download_button(
                    label=f"📥 Descargar Informe Institucional en PDF ({f.ticker})",
                    data=f_pdf.read(),
                    file_name=f"{f.ticker}_Research_Report.pdf",
                    mime="application/pdf",
                    width="stretch",
                )
        else:
            st.info("Pulsa '[Generar PDF]' en el panel lateral para compilar el documento listo para descargar.")

    else:
        st.info("👈 Selecciona un ticker en el panel lateral y pulsa **[Analizar]** o **[Generar PDF]** para visualizar el reporte completo.")
