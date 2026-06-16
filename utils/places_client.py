"""
utils/places_client.py
Enriquece cada organización con datos de Google Places API (New).
Usa la arquitectura v1 (places.googleapis.com), NO la API clásica.
Si GOOGLE_PLACES_API_KEY no está configurada o falla, retorna datos
vacíos sin romper la app (modo degradado).
"""

import json
import re
import streamlit as st
import requests
import google.generativeai as genai

_BASE = "https://places.googleapis.com/v1"
_MODEL_GEMINI = "gemini-2.5-flash"


def _get_key():
    try:
        return st.secrets["GOOGLE_PLACES_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None


def _search_text(query: str, key: str):
    """
    Text Search (New): POST a /places:searchText
    Retorna el primer place dict o None.
    """
    url = f"{_BASE}/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.location,places.rating,places.userRatingCount,"
            "places.googleMapsUri,places.internationalPhoneNumber,"
            "places.websiteUri,places.currentOpeningHours,"
            "places.businessStatus,places.photos,places.reviews"
        ),
    }
    body = {"textQuery": query, "maxResultCount": 1}

    r = requests.post(url, headers=headers, json=body, timeout=12)
    if r.status_code != 200:
        return None

    data = r.json()
    places = data.get("places", [])
    return places[0] if places else None


def _photo_url(photo_name: str, key: str, max_width: int = 600) -> str:
    """
    Place Photos (New): GET a /{photo_name}/media
    photo_name viene como 'places/XXX/photos/YYY'
    """
    return (
        f"{_BASE}/{photo_name}/media"
        f"?maxWidthPx={max_width}"
        f"&key={key}"
        f"&skipHttpRedirect=false"
    )


def _is_24h(opening_hours: dict) -> bool:
    periods = opening_hours.get("periods", []) if opening_hours else []
    for p in periods:
        open_ = p.get("open", {})
        if open_.get("day") == 0 and open_.get("hour") == 0 and open_.get("minute") == 0 and "close" not in p:
            return True
    return False


def _analyze_reviews_with_gemini(reviews: list, org_name: str) -> list:
    """
    Usa Gemini para detectar menciones estudiantiles en las reseñas.
    reviews: lista de dicts con formato Places API (New):
        {"text": {"text": "..."}, ...}
    """
    if not reviews:
        return []

    textos = "\n".join(
        f"- {r.get('text', {}).get('text', '')[:300]}"
        for r in reviews
        if r.get("text", {}).get("text")
    )
    if not textos.strip():
        return []

    prompt = f"""
Analiza las siguientes reseñas de Google Maps de "{org_name}".
Identifica ÚNICAMENTE las que mencionan experiencias estudiantiles:
prácticas, servicio social, internado, rotaciones, residencias, convenios universitarios,
clinical placement, observership, pasantías, concurrencias, o formación clínica.

Reseñas:
{textos}

Devuelve SOLO un JSON array (sin markdown) con máximo 3 elementos:
[{{"tag": "etiqueta corta", "texto": "fragmento de máximo 120 caracteres"}}]

Si no hay menciones estudiantiles, devuelve: []
""".strip()

    try:
        model = genai.GenerativeModel(_MODEL_GEMINI)
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0, max_output_tokens=512,
                response_mime_type="application/json",
            ),
        )
        raw = response.text.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception:
        return []


_EMPTY_PLACES = {
    "rating": None,
    "num_resenas": None,
    "maps_url": None,
    "foto_url": None,
    "horario_24h": None,
    "horario_detalle": [],
    "abierto_ahora": None,
    "business_status": None,
    "menciones_estudiantiles": [],
    "telefono_places": None,
    "web_places": None,
    "direccion_places": None,
}


def enrich_organization(org: dict) -> dict:
    """
    Recibe un dict de organización (de Gemini) y agrega el sub-dict 'places'.
    Usa Places API (New). Si no hay key o falla, agrega places vacío.
    """
    key = _get_key()

    if not key:
        org["places"] = dict(_EMPTY_PLACES)
        return org

    try:
        nombre    = org.get("nombre", "")
        ciudad    = org.get("ciudad", "")
        direccion = org.get("direccion", "")
        query     = f"{nombre} {direccion} {ciudad}".strip()

        place = _search_text(query, key)
        if not place:
            org["places"] = dict(_EMPTY_PLACES)
            return org

        # Foto
        photos = place.get("photos", [])
        foto_url = _photo_url(photos[0]["name"], key) if photos else None

        # Horario
        opening    = place.get("currentOpeningHours", {}) or {}
        is_24h     = _is_24h(opening)
        horario_desc = opening.get("weekdayDescriptions", [])

        # Reseñas → análisis Gemini
        reviews   = place.get("reviews", [])
        menciones = _analyze_reviews_with_gemini(reviews, nombre)

        org["places"] = {
            "rating":                  place.get("rating"),
            "num_resenas":             place.get("userRatingCount"),
            "maps_url":                place.get("googleMapsUri"),
            "foto_url":                foto_url,
            "horario_24h":             is_24h,
            "horario_detalle":         horario_desc,
            "abierto_ahora":           opening.get("openNow"),
            "business_status":        place.get("businessStatus"),
            "menciones_estudiantiles": menciones,
            "telefono_places":         place.get("internationalPhoneNumber"),
            "web_places":              place.get("websiteUri"),
            "direccion_places":        place.get("formattedAddress"),
        }

        # Enriquecer coordenadas si Gemini no las tenía
        if not org.get("coordenadas", {}).get("lat"):
            loc = place.get("location", {})
            org["coordenadas"] = {
                "lat": loc.get("latitude"),
                "lng": loc.get("longitude"),
            }

    except Exception as e:
        org["places"] = dict(_EMPTY_PLACES)
        org["places"]["_error"] = str(e)

    return org


def enrich_all(orgs: list) -> list:
    """Enriquece todas las organizaciones con Places API (New)."""
    return [enrich_organization(o) for o in orgs]
