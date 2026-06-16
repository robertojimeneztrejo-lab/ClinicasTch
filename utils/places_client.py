"""
utils/places_client.py
Enriquece cada organización con datos de Google Places API.
Si GOOGLE_PLACES_API_KEY no está configurada, retorna datos vacíos
sin romper la app (modo degradado).
"""

import streamlit as st
import requests
import google.generativeai as genai

_BASE = "https://maps.googleapis.com/maps/api/place"
_MODEL_GEMINI = "gemini-2.5-flash"


def _get_key() -> str | None:
    try:
        return st.secrets["GOOGLE_PLACES_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None


def _find_place_id(name: str, address: str, key: str) -> str | None:
    """Busca el place_id en Google Places por nombre + dirección."""
    url = f"{_BASE}/findplacefromtext/json"
    params = {
        "input":      f"{name} {address}",
        "inputtype":  "textquery",
        "fields":     "place_id",
        "key":        key,
    }
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    candidates = data.get("candidates", [])
    if candidates:
        return candidates[0].get("place_id")
    return None


def _get_place_details(place_id: str, key: str) -> dict:
    """Obtiene detalles completos de un place_id."""
    url = f"{_BASE}/details/json"
    fields = ",".join([
        "rating",
        "user_ratings_total",
        "opening_hours",
        "business_status",
        "formatted_phone_number",
        "website",
        "formatted_address",
        "geometry",
        "photos",
        "reviews",
        "url",
    ])
    params = {
        "place_id": place_id,
        "fields":   fields,
        "language": "es",
        "key":      key,
    }
    r = requests.get(url, params=params, timeout=10)
    return r.json().get("result", {})


def _photo_url(photo_reference: str, key: str, max_width: int = 600) -> str:
    return (
        f"{_BASE}/photo"
        f"?maxwidth={max_width}"
        f"&photo_reference={photo_reference}"
        f"&key={key}"
    )


def _analyze_reviews_with_gemini(reviews: list[dict], org_name: str) -> list[dict]:
    """
    Usa Gemini para detectar menciones estudiantiles en las reseñas de Google.
    Retorna lista de {"tag": str, "texto": str}.
    """
    if not reviews:
        return []

    textos = "\n".join(
        f"- {r.get('text','')[:300]}" for r in reviews if r.get("text")
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
[
  {{"tag": "etiqueta corta (ej: Prácticas, Residentes, Convenio, Clinical placement)",
    "texto": "fragmento relevante de máximo 120 caracteres"}}
]

Si no hay menciones estudiantiles, devuelve: []
""".strip()

    try:
        model    = genai.GenerativeModel(_MODEL_GEMINI)
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(temperature=0, max_output_tokens=512),
        )
        import json, re
        raw   = response.text.strip()
        raw   = re.sub(r"^```json\s*", "", raw)
        raw   = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception:
        return []


def enrich_organization(org: dict) -> dict:
    """
    Recibe un dict de organización (de Gemini) y agrega el sub-dict 'places'.
    Si no hay API key, agrega places vacío sin errores.
    """
    key = _get_key()

    empty_places = {
        "rating":                None,
        "num_resenas":           None,
        "maps_url":              None,
        "foto_url":              None,
        "horario_24h":           None,
        "abierto_ahora":         None,
        "business_status":       None,
        "menciones_estudiantiles": [],
        "telefono_places":       None,
        "web_places":            None,
        "direccion_places":      None,
    }

    if not key:
        org["places"] = empty_places
        return org

    try:
        nombre   = org.get("nombre", "")
        direccion = org.get("direccion", "") + " " + org.get("ciudad", "")

        place_id = _find_place_id(nombre, direccion, key)
        if not place_id:
            org["places"] = empty_places
            return org

        details = _get_place_details(place_id, key)

        # Foto
        photos = details.get("photos", [])
        foto_url = (
            _photo_url(photos[0]["photo_reference"], key)
            if photos else None
        )

        # Horario
        opening = details.get("opening_hours", {})
        periods  = opening.get("periods", [])
        is_24h   = any(
            p.get("open", {}).get("time") == "0000" and "close" not in p
            for p in periods
        )

        # Reseñas → análisis Gemini
        reviews  = details.get("reviews", [])
        menciones = _analyze_reviews_with_gemini(reviews, nombre)

        org["places"] = {
            "rating":                  details.get("rating"),
            "num_resenas":             details.get("user_ratings_total"),
            "maps_url":                details.get("url"),
            "foto_url":                foto_url,
            "horario_24h":             is_24h,
            "abierto_ahora":           opening.get("open_now"),
            "business_status":         details.get("business_status"),
            "menciones_estudiantiles": menciones,
            "telefono_places":         details.get("formatted_phone_number"),
            "web_places":              details.get("website"),
            "direccion_places":        details.get("formatted_address"),
        }

        # Enriquecer coordenadas si Gemini no las tenía
        if not org.get("coordenadas", {}).get("lat"):
            geo = details.get("geometry", {}).get("location", {})
            org["coordenadas"] = {
                "lat": geo.get("lat"),
                "lng": geo.get("lng"),
            }

    except Exception as e:
        org["places"] = empty_places
        org["places"]["_error"] = str(e)

    return org


def enrich_all(orgs: list[dict]) -> list[dict]:
    """Enriquece todas las organizaciones con Places API."""
    return [enrich_organization(o) for o in orgs]
