# 📈 Private Equity Research & Portfolio Lab

Sistema modular y automatizado en Python para análisis de activos, gestión táctica de cartera (PPI) y generación de reportes institucionales de inversión en PDF con **Google Gemini (GenAI)** y **Playwright Headless**, integrado en una interfaz web interactiva con **Streamlit**.

---

## 🏛️ Características Principales

1. **Dashboard Web Interactivo con Streamlit (`app.py`)**:
   - **Visualización de Cartera en Tiempo Real**: Conexión con Portfolio Personal Inversiones (PPI) para saldos líquidos (ARS y USD) y tenencias vigentes.
   - **Chat Asesor Financiero (CIO Mode)**: Asesor conversacional con memoria contextual que recomienda operaciones, rotaciones y dimensionamiento de posición respetando la liquidez disponible de la cuenta.
   - **Terminal de Research & Visor de Reportes**: Visualización de métricas clave, gráficos generados y descarga inmediata de PDFs vectoriales.

2. **Extracción Cuantitativa Determinista**:
   - **Fundamentales Contables**: Ingresos históricos, EPS diluido, márgenes (bruto, operativo, neto), solvencia, deuda y múltiplos P/E (trailing vs. forward) vía `yfinance`.
   - **Análisis Técnico Vectorizado**: Medias móviles simples (SMA 50 / 200), RSI 14, ATR de volatilidad y detección matemática de soportes y resistencias dinámicos.
   - **Ratios CEDEARs BYMA**: Conversión automática a ratios locales (MELI 60:1, AAPL 10:1, MSFT 30:1, etc.).

3. **Motor Analítico con Google Gemini (GenAI SDK)**:
   - Salida 100% estructurada mediante schemas Pydantic (`InvestmentReportAIResult`).
   - Sistema de contingencia multinivel (`gemini-3.7-flash`, `gemini-3.5-flash`, `gemini-3.8-flash`).

4. **Compilación de PDF Nativo con Playwright**:
   - Renderizado Chromium headless de alta fidelidad basado en plantillas HTML5 + Jinja2 y CSS editorial moderno.
   - Gráficos generados a 200-300 DPI con Matplotlib/Seaborn.

---

## 🚀 Inicio Rápido

### 1. Requisitos e Instalación
Asegúrate de contar con Python 3.10+ y ejecuta:

```bash
# Instalar dependencias
pip install -r requirements.txt

# Instalar navegador para Playwright (sólo la primera vez)
python -m playwright install chromium
```

### 2. Configurar Variables de Entorno (`.env`)
Crea un archivo `.env` en la raíz (puedes guiarte con `.env.example`):

```env
# Clave de Google Gemini (AI Studio)
GEMINI_API_KEY=tu_gemini_api_key

# Credenciales de Portfolio Personal Inversiones (PPI)
PPI_AUTHORIZED_CLIENT=API_CLI_REST
PPI_CLIENT_KEY=tu_client_key_de_ppi
PPI_API_KEY=tu_api_key_de_ppi
PPI_API_SECRET=tu_api_secret_de_ppi
PPI_ACCOUNT_NUMBER=tu_numero_de_comitente
```

*(Si no dispones de claves de PPI o Gemini al momento de probar, el sistema activará automáticamente carteras de demostración y motores analíticos de contingencia).*

---

## 🖥️ Ejecutar la Aplicación Web

Inicia la interfaz gráfica interactiva con el comando:

```bash
streamlit run app.py
```

La aplicación se abrirá automáticamente en tu navegador predeterminado en `http://localhost:8501`.

---

## 💻 Ejecución Alternativa por Consola (CLI)

También puedes compilar informes en PDF directamente desde la terminal:

```bash
# Analizar y generar PDF en vivo
python main.py MELI

# Generar y abrir el PDF automáticamente en tu visor
python main.py AAPL --open

# Modo simulado de prueba (sin consumo de tokens)
python main.py MSFT --mock --open
```

Los informes quedan compilados en:
- **PDFs**: `output/reports/{TICKER}_research_report.pdf`
- **Gráficos**: `output/generated_charts/{TICKER}_technical.png` y `output/generated_charts/{TICKER}_financial.png`

---

## 📂 Arquitectura del Proyecto

```text
investment-agent/
├── data/
│   ├── schemas.py          # Modelos de datos Pydantic
│   ├── fundamental.py      # Extracción contable con yfinance
│   ├── technical.py        # Medias, RSI, ATR y niveles pivote
│   ├── ppi_client.py       # Cliente REST para Portfolio Personal Inversiones (PPI)
│   └── pipeline.py         # Fachada unificada get_asset_payload()
├── charts/
│   ├── technical_chart.py  # Gráficos técnicos con Matplotlib/Seaborn
│   └── financial_chart.py  # Gráficos de barras de Ingresos vs. EPS
├── engine/
│   ├── prompts.py          # Schemas y prompts del reporte institucional
│   ├── analyzer.py         # Orquestador con Google GenAI Structured Outputs
│   ├── advisor_prompt.py   # System Prompt del CIO interactivo
│   └── advisor_agent.py    # PortfolioAdvisor para el chat conversacional
├── templates/
│   ├── report_template.html# Plantilla editorial en HTML5 con Jinja2
│   └── styles.css          # Estilos CSS modernos con reglas @media print
├── exporter/
│   └── pdf_generator.py    # Compilador Playwright Chromium Headless
├── output/
│   ├── reports/            # PDFs e informes HTML generados
│   └── generated_charts/   # Gráficos estáticos en alta resolución
├── app.py                  # Aplicación Web principal con Streamlit
├── main.py                 # CLI/Orquestador de terminal
├── config.py               # Gestión de settings con Pydantic
└── requirements.txt        # Dependencias fijadas del proyecto
```
