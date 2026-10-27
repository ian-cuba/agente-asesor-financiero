from datetime import datetime, timezone
import logging
from data.schemas import AssetPayload
from data.fundamental import fetch_fundamental_data
from data.technical import fetch_technical_data

logger = logging.getLogger(__name__)


def get_asset_payload(ticker: str) -> AssetPayload:
    """
    Descarga y consolida el perfil fundamental y técnico de un activo dado en un modelo Pydantic estructurado.
    """
    clean_ticker = ticker.strip().upper()
    logger.info(f"Consolidando payload completo para {clean_ticker}...")

    # 1. Datos Fundamentales
    fundamentals = fetch_fundamental_data(clean_ticker)

    # 2. Datos Técnicos
    _, technicals = fetch_technical_data(clean_ticker)

    payload = AssetPayload(
        ticker=clean_ticker,
        timestamp=datetime.now(timezone.utc),
        fundamentals=fundamentals,
        technicals=technicals,
    )
    return payload
