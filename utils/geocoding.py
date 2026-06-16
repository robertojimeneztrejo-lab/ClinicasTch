"""
utils/geocoding.py
Convierte una referencia de ubicación en lenguaje natural ("Polanco" +
"México") a coordenadas lat/lng exactas, usando Google Geocoding API.

Esto permite que el radio de búsqueda (1-5 km) sea un cálculo matemático
real en vez de una interpretación aproximada del modelo de lenguaje.
Usa la MISMA API key que Places (GOOGLE_PLACES_API_KEY) — Geocoding API
se activa por separado en Google Cloud Console pero comparte facturación.
"""

import streamlit as st
import requests

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def _get_key():
    try:
        return st.secrets["GOOGLE_PLACES_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None


def geocode_location(referencia: str, pais: str) -> dict:
    """
    Geocodifica una referencia + país a coordenadas exactas.

    Retorna:
        {
            "lat": float | None,
            "lng": float | None,
            "direccion_formateada": str | None,
            "encontrado": bool,
            "error": str | None,
        }
    """
    key = _get_key()
    resultado_vacio = {
        "lat": None, "lng": None,
        "direccion_formateada": None,
        "encontrado": False,
        "error": None,
    }

    if not key:
        resultado_vacio["error"] = "GOOGLE_PLACES_API_KEY no configurada"
        return resultado_vacio

    query = f"{referencia}, {pais}".strip(", ")

    try:
        r = requests.get(
            _GEOCODE_URL,
            params={"address": query, "key": key, "language": "es"},
            timeout=10,
        )
        data = r.json()

        if data.get("status") != "OK" or not data.get("results"):
            resultado_vacio["error"] = data.get("status", "SIN_RESULTADOS")
            return resultado_vacio

        primero = data["results"][0]
        loc     = primero["geometry"]["location"]

        return {
            "lat": loc["lat"],
            "lng": loc["lng"],
            "direccion_formateada": primero.get("formatted_address"),
            "encontrado": True,
            "error": None,
        }

    except Exception as e:
        resultado_vacio["error"] = str(e)
        return resultado_vacio
