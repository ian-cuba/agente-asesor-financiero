from __future__ import annotations
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid

from config import OUTPUT_DIR

logger = logging.getLogger(__name__)

CHATS_DIR = OUTPUT_DIR / "chats"
CHATS_DIR.mkdir(parents=True, exist_ok=True)


def list_saved_chats() -> List[Dict[str, Any]]:
    """Retorna la lista de conversaciones guardadas ordenadas de más reciente a más antigua."""
    chats: List[Dict[str, Any]] = []
    for f in CHATS_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                chats.append({
                    "id": data.get("id", f.stem),
                    "title": data.get("title", "Conversación sin título"),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "message_count": len(data.get("messages", [])),
                })
        except Exception as e:
            logger.warning(f"Error leyendo archivo de chat {f}: {e}")

    # Ordenar por fecha de última actualización descendente
    chats.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at")), reverse=True)
    return chats


def load_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    """Carga los mensajes y metadatos de un chat específico."""
    chat_file = CHATS_DIR / f"{chat_id}.json"
    if not chat_file.exists():
        return None
    try:
        with open(chat_file, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception as e:
        logger.error(f"Error cargando chat {chat_id}: {e}")
        return None


def save_chat(chat_id: str, title: str, messages: List[Dict[str, str]], created_at: Optional[str] = None) -> bool:
    """Guarda o actualiza una sesión de conversación en disco."""
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chat_file = CHATS_DIR / f"{chat_id}.json"

    data = {
        "id": chat_id,
        "title": title.strip() or "Consulta de Cartera",
        "created_at": created_at or now_iso,
        "updated_at": now_iso,
        "messages": messages,
    }

    try:
        with open(chat_file, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error guardando chat {chat_id}: {e}")
        return False


def delete_chat(chat_id: str) -> bool:
    """Elimina una sesión de chat guardada."""
    chat_file = CHATS_DIR / f"{chat_id}.json"
    if chat_file.exists():
        try:
            chat_file.unlink()
            return True
        except Exception as e:
            logger.error(f"Error borrando chat {chat_id}: {e}")
            return False
    return False


def create_new_chat_session() -> Dict[str, Any]:
    """Genera una nueva estructura de sesión de chat en blanco con el saludo inicial."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    uid = uuid.uuid4().hex[:6]
    chat_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uid}"

    initial_messages = [
        {
            "role": "assistant",
            "content": (
                "👋 **Bienvenido al Portfolio Lab**. "
                "Soy tu Chief Investment Officer (CIO) y Asesor Financiero personal. "
                "Tengo acceso en tiempo real a tus tenencias de cartera, saldos líquidos y precios de mercado.\n\n"
                "¿Qué activo o estrategia deseas evaluar hoy? Puedes consultarme sobre **sizing**, **rotaciones de cartera** "
                "o pedirme analizar un activo específico (ej: *'Analiza MELI'*, *'¿Conviene sumar AAPL hoy?'*)."
            ),
        }
    ]

    new_chat = {
        "id": chat_id,
        "title": f"Consulta #{uid}",
        "created_at": now_str,
        "updated_at": now_str,
        "messages": initial_messages,
    }
    save_chat(chat_id, new_chat["title"], initial_messages, created_at=now_str)
    return new_chat
