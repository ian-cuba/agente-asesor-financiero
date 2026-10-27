from __future__ import annotations
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import requests

from config import settings

logger = logging.getLogger(__name__)


class PositionRecord(BaseModel):
    """Posición individual en cartera de inversión."""
    ticker: str = Field(description="Ticker del activo local o internacional (ej. 'MELI', 'AL30')")
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, description="Tipo de instrumento (ej. CEDEARS, ACCIONES, BONOS, FCI, ONS)")
    quantity: float = Field(default=0.0, description="Cantidad nominal de títulos en tenencia")
    current_price: Optional[float] = Field(default=None, description="Precio de mercado actual")
    total_value_ars: Optional[float] = Field(default=None, description="Valuación total en Pesos")
    total_value_usd: Optional[float] = Field(default=None, description="Valuación estimada en USD CCL / MEP")
    portfolio_weight_pct: Optional[float] = Field(default=None, description="Ponderación porcentual sobre la cartera total")


class PortfolioSummary(BaseModel):
    """Resumen consolidado de saldos líquidos y tenencias en PPI."""
    account_number: str
    total_equity_ars: float = Field(default=0.0, description="Patrimonio total en Pesos")
    total_equity_usd: float = Field(default=0.0, description="Patrimonio total en Dólares")
    available_cash_ars: float = Field(default=0.0, description="Saldo disponible en ARS")
    available_cash_usd: float = Field(default=0.0, description="Saldo disponible en USD")
    positions: List[PositionRecord] = Field(default_factory=list)


class PPIClient:
    """
    Cliente REST seguro de sólo lectura para Portfolio Personal Inversiones (PPI).
    Recupera saldos líquidos, tenencias y ponderaciones para personalizar el sizing de la recomendación.
    """

    BASE_URL = "https://clientapi.portfoliopersonal.com/api/1.0"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        authorized_client: Optional[str] = None,
        client_key: Optional[str] = None,
        account_number: Optional[str] = None,
    ):
        self.api_key = api_key or settings.PPI_API_KEY
        self.api_secret = api_secret or settings.PPI_API_SECRET
        self.authorized_client = authorized_client or getattr(settings, "PPI_AUTHORIZED_CLIENT", "API_CLI_REST")
        self.client_key = client_key or getattr(settings, "PPI_CLIENT_KEY", self.api_key)
        self.account_number = account_number or settings.PPI_ACCOUNT_NUMBER or ""
        self._session = requests.Session()
        self._token: Optional[str] = None
        self._auth_attempted: bool = False
        self._cached_summary: Optional[PortfolioSummary] = None
        self.last_error: Optional[str] = None
        self.is_demo_mode: bool = True

    @property
    def is_configured(self) -> bool:
        """Determina si las credenciales de PPI están cargadas."""
        return bool(self.api_key and self.api_secret and not self.api_key.startswith("tu_ppi_api_key"))

    def authenticate(self) -> bool:
        """
        Autentica contra el endpoint oficial de PPI para obtener el Bearer Token de sesión.
        """
        if self._auth_attempted:
            return bool(self._token)
        self._auth_attempted = True

        if not self.is_configured:
            self.last_error = "Credenciales de PPI no configuradas en el archivo .env."
            logger.info(self.last_error)
            return False

        try:
            client_key = self.client_key if self.client_key else self.api_key
            headers = {
                "AuthorizedClient": self.authorized_client,
                "ClientKey": client_key,
                "ApiKey": self.api_key,
                "ApiSecret": self.api_secret,
                "Content-Type": "application/json",
            }
            resp = self._session.post(f"{self.BASE_URL}/Account/LoginApi", headers=headers, json={}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    self._token = data[0].get("accessToken")
                elif isinstance(data, dict):
                    self._token = data.get("accessToken") or data.get("token")
                
                if self._token:
                    headers_update: Dict[str, str] = {"Authorization": f"Bearer {self._token}"}
                    if self.authorized_client:
                        headers_update["AuthorizedClient"] = self.authorized_client
                    if self.client_key:
                        headers_update["ClientKey"] = self.client_key
                    self._session.headers.update(headers_update)
                    logger.info("Autenticación exitosa con PPI.")
                    self.last_error = None
                    return True
                else:
                    self.last_error = "Respuesta de PPI recibida pero sin accessToken de sesión."
                    logger.warning(self.last_error)
                    return False
            else:
                raw_err = resp.text.strip()
                if "Credentials invalid" in raw_err:
                    self.last_error = (
                        "Credenciales de PPI inválidas (400 Credentials invalid). "
                        "Verifica en PPI (Gestiones -> Gestión de servicio API) que AuthorizedClient, ClientKey, ApiKey y ApiSecret coincidan exactamente."
                    )
                else:
                    self.last_error = f"Error autenticando contra PPI (Status {resp.status_code}): {raw_err[:120]}"
                logger.warning(self.last_error)
                return False
        except Exception as e:
            self.last_error = f"Excepción de conexión contra PPI: {e}"
            logger.warning(self.last_error)
            return False

    def fetch_portfolio_summary(self) -> PortfolioSummary:
        """
        Recupera saldos y posiciones de la cuenta comitente en PPI.
        Si la API no está configurada, retorna un portfolio base seguro para no interrumpir el pipeline.
        """
        if self._cached_summary is not None:
            return self._cached_summary

        if not self.is_configured:
            self.is_demo_mode = True
            self._cached_summary = self._get_fallback_portfolio()
            return self._cached_summary

        if not self._token and not self.authenticate():
            self.is_demo_mode = True
            self._cached_summary = self._get_fallback_portfolio()
            return self._cached_summary

        if not self.account_number:
            self.last_error = (
                "Autenticación exitosa en PPI, pero falta configurar PPI_ACCOUNT_NUMBER en tu .env "
                "con tu número de cuenta comitente."
            )
            logger.warning(self.last_error)
            self.is_demo_mode = True
            self._cached_summary = self._get_fallback_portfolio()
            return self._cached_summary

        try:
            resp = self._session.get(
                f"{self.BASE_URL}/Account/BalancesAndPositions?accountNumber={self.account_number}",
                timeout=12,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._cached_summary = self._parse_ppi_response(data)
                self.is_demo_mode = False
                self.last_error = None
                return self._cached_summary
            else:
                self.last_error = f"Endpoint de saldos PPI devolvió status {resp.status_code} para comitente {self.account_number}."
                logger.warning(self.last_error)
                self.is_demo_mode = True
                self._cached_summary = self._get_fallback_portfolio()
                return self._cached_summary
        except Exception as e:
            self.last_error = f"Fallo al consultar tenencias en PPI: {e}"
            logger.warning(self.last_error)
            self.is_demo_mode = True
            self._cached_summary = self._get_fallback_portfolio()
            return self._cached_summary

    def get_ticker_position(self, ticker: str) -> Optional[PositionRecord]:
        """Busca si el ticker (o su versión CEDEAR) se encuentra en la cartera actual."""
        summary = self.fetch_portfolio_summary()
        clean = ticker.upper()
        for pos in summary.positions:
            if clean in pos.ticker.upper():
                return pos
        return None

    def calculate_sizing_suggestion(
        self,
        ticker: str,
        current_price_usd: float,
        suggested_weight_pct: float,
        cedear_ratio: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calcula exactamente cuántos nominales adquirir o recortar según el capital de la cuenta.
        """
        summary = self.fetch_portfolio_summary()
        total_usd = summary.total_equity_usd or 50000.0  # Base estándar
        target_allocation_usd = total_usd * (suggested_weight_pct / 100.0)

        existing_pos = self.get_ticker_position(ticker)
        current_holding_usd: float = float(existing_pos.total_value_usd) if (existing_pos and existing_pos.total_value_usd is not None) else 0.0
        current_weight_pct = (current_holding_usd / total_usd) * 100.0 if total_usd > 0 else 0.0

        diff_usd = target_allocation_usd - current_holding_usd

        # Si cuenta con ratio CEDEAR, calculamos el precio de cada CEDEAR individual en USD
        ratio = cedear_ratio or 1.0
        cedear_unit_price_usd = current_price_usd / ratio

        suggested_cedear_qty = max(0, int(diff_usd / cedear_unit_price_usd)) if cedear_unit_price_usd > 0 else 0

        action = "MANTENER"
        if diff_usd > (total_usd * 0.01):
            action = "INCREMENTAR / COMPRAR"
        elif diff_usd < -(total_usd * 0.01):
            action = "RECORTAR / TOMAR GANANCIA"

        return {
            "ticker": ticker.upper(),
            "portfolio_total_equity_usd": round(total_usd, 2),
            "current_holding_usd": round(current_holding_usd, 2),
            "current_weight_pct": round(current_weight_pct, 2),
            "suggested_weight_pct": round(suggested_weight_pct, 2),
            "target_allocation_usd": round(target_allocation_usd, 2),
            "capital_to_deploy_usd": round(diff_usd, 2),
            "cedear_ratio": ratio,
            "cedear_unit_price_usd": round(cedear_unit_price_usd, 2),
            "suggested_cedear_nominal_qty": suggested_cedear_qty,
            "operational_action": action,
        }

    def _parse_ppi_response(self, data: Dict[str, Any]) -> PortfolioSummary:
        """Parsea el payload devuelto por la API oficial de PPI (groupedAvailability y groupedInstruments)."""
        # Estimar tipo de cambio implícito (CCL / MEP) a partir de instrumentos en USD o fallback a 1500
        usd_rate = 1500.0
        for g in data.get("groupedInstruments", []):
            if g.get("name") in ["ONS", "BONOS", "CEDEARS"]:
                for inst in g.get("instruments", []):
                    amt = float(inst.get("amount", 0.0))
                    if "dolar" in str(inst.get("currency", "")).lower() and amt > 0:
                        grouped_val = float(g.get("groupedValue", 0.0))
                        if grouped_val > 0:
                            usd_rate = grouped_val / amt
                            break
                if usd_rate != 1500.0:
                    break

        # Saldos líquidos de disponibilidad
        cash_ars = 0.0
        cash_usd = 0.0
        for group in data.get("groupedAvailability", []):
            curr = str(group.get("currency", "")).lower()
            for item in group.get("availability", []):
                amt = float(item.get("amount", 0.0))
                if "pesos" in curr or "ars" in curr:
                    cash_ars += amt
                elif "dolar" in curr or "usd" in curr:
                    cash_usd += amt

        # Si PPI devuelve el schema plano anterior
        if "totalEquityArs" in data and not data.get("groupedInstruments"):
            cash_ars = float(data.get("availableCashArs", 0.0))
            cash_usd = float(data.get("availableCashUsd", 0.0))

        # Instrumentos e inversiones en tenencia
        positions: List[PositionRecord] = []
        total_instruments_ars = 0.0

        for group in data.get("groupedInstruments", []):
            cat_name = str(group.get("name", "OTRO")).strip().upper()
            total_instruments_ars += float(group.get("groupedValue", 0.0))
            for inst in group.get("instruments", []):
                ticker = str(inst.get("ticker", "")).strip().upper()
                qty = float(inst.get("quantity", 0.0))
                price = float(inst.get("price", 0.0))
                amt = float(inst.get("amount", 0.0))
                curr = str(inst.get("currency", "")).lower()
                desc = inst.get("description")

                if "dolar" in curr or "usd" in curr:
                    val_usd = amt
                    val_ars = val_usd * usd_rate
                else:
                    val_ars = amt
                    val_usd = val_ars / usd_rate if usd_rate > 0 else 0.0

                positions.append(
                    PositionRecord(
                        ticker=ticker,
                        description=desc,
                        category=cat_name,
                        quantity=qty,
                        current_price=price,
                        total_value_ars=round(val_ars, 2),
                        total_value_usd=round(val_usd, 2),
                        portfolio_weight_pct=0.0,
                    )
                )

        # Si vino en formato positions plano:
        if not positions and data.get("positions"):
            for raw_pos in data.get("positions", []):
                t = str(raw_pos.get("ticker", "")).strip().upper()
                qty = float(raw_pos.get("quantity", 0.0))
                val_ars = float(raw_pos.get("totalValueArs", 0.0)) if raw_pos.get("totalValueArs") else None
                val_usd = float(raw_pos.get("totalValueUsd", 0.0)) if raw_pos.get("totalValueUsd") else None
                positions.append(
                    PositionRecord(
                        ticker=t,
                        description=raw_pos.get("description"),
                        quantity=qty,
                        current_price=raw_pos.get("price"),
                        total_value_ars=val_ars,
                        total_value_usd=val_usd,
                    )
                )

        # Valuación patrimonial consolidada
        total_equity_ars = total_instruments_ars + cash_ars + (cash_usd * usd_rate)
        if total_equity_ars <= 0 and "totalEquityArs" in data:
            total_equity_ars = float(data.get("totalEquityArs", 0.0))
            total_equity_usd = float(data.get("totalEquityUsd", 0.0))
        else:
            total_equity_usd = total_equity_ars / usd_rate if usd_rate > 0 else 0.0

        # Calcular ponderación porcentual real sobre la cartera total
        for pos in positions:
            if total_equity_ars > 0 and pos.total_value_ars is not None:
                pos.portfolio_weight_pct = round((pos.total_value_ars / total_equity_ars) * 100.0, 2)

        return PortfolioSummary(
            account_number=self.account_number,
            total_equity_ars=round(total_equity_ars, 2),
            total_equity_usd=round(total_equity_usd, 2),
            available_cash_ars=round(cash_ars, 2),
            available_cash_usd=round(cash_usd, 2),
            positions=positions,
        )

    def _get_fallback_portfolio(self) -> PortfolioSummary:
        """Cartera de referencia cuando no se dispone de credenciales PPI conectadas."""
        return PortfolioSummary(
            account_number="DEMO-PORTFOLIO",
            total_equity_ars=60000000.0,
            total_equity_usd=50000.0,
            available_cash_ars=5000000.0,
            available_cash_usd=4200.0,
            positions=[
                PositionRecord(ticker="SPY", description="CEDEAR SPDR S&P 500", quantity=150, total_value_usd=5200.0, portfolio_weight_pct=10.4),
                PositionRecord(ticker="AAPL", description="CEDEAR Apple Inc.", quantity=200, total_value_usd=4600.0, portfolio_weight_pct=9.2),
                PositionRecord(ticker="MELI", description="CEDEAR MercadoLibre", quantity=60, total_value_usd=1810.0, portfolio_weight_pct=3.62),
            ],
        )
