"""
utils/supabase_client.py
Conexión a Supabase y helpers de persistencia.

Esquema SQL a ejecutar en Supabase (Dashboard → SQL Editor):

CREATE TABLE searches (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz DEFAULT now(),
    location    text,
    pais        text,
    lat         float,
    lng         float,
    radius_km   int,
    min_specs   int,
    max_results int,
    perfil_json jsonb
);

CREATE TABLE results (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    search_id               uuid REFERENCES searches(id) ON DELETE CASCADE,
    created_at              timestamptz DEFAULT now(),
    nombre                  text,
    tipo_institucion        text,
    tipo_institucion_label  text,
    pais                    text,
    ciudad                  text,
    direccion               text,
    lat                     float,
    lng                     float,
    distancia_km            float,
    telefono                text,
    email                   text,
    sitio_web               text,
    jefe_ensenanza          text,
    cargo_jefe              text,
    jefe_verificado         boolean DEFAULT false,
    especialidades          jsonb,
    modalidades             text[],
    score_global            float,
    rating_google           float,
    num_resenas             int,
    maps_url                text,
    foto_url                text,
    horario_24h             boolean,
    horario_atencion        text,
    abierto_ahora           boolean,
    menciones_estud         jsonb,
    justificacion           text,
    raw_json                jsonb
);

CREATE INDEX idx_searches_created_at ON searches(created_at DESC);
CREATE INDEX idx_results_search_id   ON results(search_id);
CREATE INDEX idx_results_score       ON results(score_global DESC);
"""

import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


def save_search(filters: dict, perfil: dict) -> str:
    """Guarda los filtros de búsqueda (ubicación geocodificada) y retorna el search_id."""
    sb = get_supabase()
    data = {
        "location":    filters.get("location", ""),
        "pais":        filters.get("pais", ""),
        "lat":         filters.get("lat"),
        "lng":         filters.get("lng"),
        "radius_km":   filters.get("radius_km", 3),
        "min_specs":   filters.get("min_specs", 1),
        "max_results": filters.get("max_results", 50),
        "perfil_json": perfil,
    }
    resp = sb.table("searches").insert(data).execute()
    return resp.data[0]["id"]


def save_results(search_id: str, orgs: list):
    """Guarda la lista de organizaciones vinculadas a un search_id."""
    sb = get_supabase()
    rows = []
    for o in orgs:
        rows.append({
            "search_id":              search_id,
            "nombre":                 o.get("nombre"),
            "tipo_institucion":       o.get("tipo_institucion"),
            "tipo_institucion_label": o.get("tipo_institucion_label"),
            "pais":                   o.get("pais"),
            "ciudad":                 o.get("ciudad"),
            "direccion":              o.get("direccion"),
            "lat":                    o.get("coordenadas", {}).get("lat"),
            "lng":                    o.get("coordenadas", {}).get("lng"),
            "distancia_km":           o.get("distancia_km_aproximada"),
            "telefono":               o.get("contacto_telefono"),
            "email":                  o.get("contacto_email"),
            "sitio_web":              o.get("sitio_web"),
            "jefe_ensenanza":         o.get("jefe_ensenanza", {}).get("nombre"),
            "cargo_jefe":             o.get("jefe_ensenanza", {}).get("cargo"),
            "jefe_verificado":        o.get("jefe_ensenanza", {}).get("verificado", False),
            "especialidades":        o.get("especialidades", []),
            "modalidades":            o.get("modalidades_aplicables", []),
            "score_global":           o.get("scores", {}).get("score_global"),
            "rating_google":          o.get("places", {}).get("rating"),
            "num_resenas":            o.get("places", {}).get("num_resenas"),
            "maps_url":               o.get("places", {}).get("maps_url"),
            "foto_url":               o.get("places", {}).get("foto_url"),
            "horario_24h":            o.get("places", {}).get("horario_24h"),
            "horario_atencion":       o.get("horario_atencion"),
            "abierto_ahora":          o.get("places", {}).get("abierto_ahora"),
            "menciones_estud":        o.get("places", {}).get("menciones_estudiantiles", []),
            "justificacion":          o.get("justificacion"),
            "raw_json":               o,
        })
    sb.table("results").insert(rows).execute()


def load_history(limit: int = 20) -> list:
    """Carga el historial de búsquedas más recientes."""
    sb = get_supabase()
    resp = (
        sb.table("searches")
        .select("id, created_at, location, pais, radius_km")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data


def load_search_results(search_id: str) -> list:
    """Carga los resultados de una búsqueda guardada."""
    sb = get_supabase()
    resp = (
        sb.table("results")
        .select("*")
        .eq("search_id", search_id)
        .order("score_global", desc=True)
        .execute()
    )
    return resp.data
