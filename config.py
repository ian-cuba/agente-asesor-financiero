from pathlib import Path
from typing import Dict, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# Directorios base del proyecto
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHARTS_DIR = BASE_DIR / "charts"
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"
GENERATED_CHARTS_DIR = OUTPUT_DIR / "generated_charts"

for d in (OUTPUT_DIR, REPORTS_DIR, GENERATED_CHARTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="API Key para Google GenAI")
    PPI_AUTHORIZED_CLIENT: Optional[str] = Field(default="API_CLI_REST", description="AuthorizedClient de PPI")
    PPI_CLIENT_KEY: Optional[str] = Field(default=None, description="ClientKey de PPI")
    PPI_API_KEY: Optional[str] = Field(default=None, description="API Key pública de PPI")
    PPI_API_SECRET: Optional[str] = Field(default=None, description="Secret Key de PPI")
    PPI_ACCOUNT_NUMBER: Optional[str] = Field(default=None, description="Número de comitente opcional")

    # Parámetros del modelo LLM
    DEFAULT_GEMINI_MODEL: str = "gemini-3.5-flash"
    REASONING_GEMINI_MODEL: str = "gemini-3.5-pro"

    # Seguridad y Acceso
    APP_PASSWORD: Optional[str] = Field(default=None, description="Contraseña de acceso a la aplicación")

    # Entorno
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"


# Ratios de conversión CEDEAR : Acción Original (Subyacente)
# Ejemplo: MELI 120:1 significa que 120 CEDEARs representan 1 acción ordinaria en Wall Street
CEDEAR_RATIOS: Dict[str, float] = {
    "AAPL": 10.0,
    "MELI": 120.0,
    "MSFT": 30.0,
    "GOOGL": 58.0,
    "AMZN": 144.0,
    "NVDA": 24.0,
    "TSLA": 15.0,
    "KO": 5.0,
    "SPY": 20.0,
    "QQQ": 20.0,
    "BABA": 9.0,
    "V": 18.0,
    "META": 24.0,
    "WMT": 6.0,
    "DIS": 12.0,
}


def get_cedear_ratio(ticker: str) -> Optional[float]:
    """Retorna el ratio CEDEAR:Acción si se conoce para el ticker dado."""
    return CEDEAR_RATIOS.get(ticker.upper())


settings = Settings()
