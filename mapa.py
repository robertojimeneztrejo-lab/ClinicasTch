"""
components/mapa.py
Renderiza el mapa georreferenciado con Folium + streamlit-folium.
"""

import folium
from streamlit_folium import st_folium


_TIPO_COLORES = {
    "hospital_publico":      "#185FA5",
    "hospital_privado":      "#854F0B",
    "hospital_universitario":"#3B6D11",
    "instituto_nacional":    "#533AB7",
    "clinica_policlinico":   "#185FA5",
    "atencion_primaria":     "#0F6E56",
    "salud_comunitaria":     "#0F6E56",
    "clinica_universitaria": "#3B6D11",
    "imss_issste":           "#185FA5",
    "sanatorio":             "#854F0B",
    "investigacion_clinica": "#533AB7",
}


def _score_color(score: float) -> str:
    if score >= 85:
        return "#3B6D11"
    if score >= 70:
        return "#185FA5"
    return "#854F0B"


def render_map(orgs: list[dict], center_lat: float = 19.43, center_lng: float = -99.13):
    """
    Renderiza el mapa con un pin por organización.
    orgs: lista de dicts enriquecidos (Gemini + Places).
    """
    # Calcular centro real si hay coords
    lats = [o["coordenadas"]["lat"] for o in orgs if o.get("coordenadas", {}).get("lat")]
    lngs = [o["coordenadas"]["lng"] for o in orgs if o.get("coordenadas", {}).get("lng")]

    if lats:
        center_lat = sum(lats) / len(lats)
        center_lng = sum(lngs) / len(lngs)

    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=5 if len(set(o.get("pais") for o in orgs)) > 1 else 11,
        tiles="CartoDB positron",
    )

    for i, org in enumerate(orgs):
        coords = org.get("coordenadas", {})
        lat = coords.get("lat")
        lng = coords.get("lng")
        if not lat or not lng:
            continue

        score  = org.get("scores", {}).get("score_global", 0)
        color  = _score_color(score)
        nombre = org.get("nombre", "Sin nombre")
        ciudad = org.get("ciudad", "")
        pais   = org.get("pais", "")
        rating = org.get("places", {}).get("rating")
        specs  = len(org.get("especialidades", []))

        rating_html = (
            f"⭐ {rating}" if rating else "Sin calificación"
        )

        popup_html = f"""
        <div style="font-family:sans-serif;min-width:200px">
            <div style="font-weight:600;font-size:13px;margin-bottom:4px">{nombre}</div>
            <div style="font-size:11px;color:#666;margin-bottom:6px">{ciudad}, {pais}</div>
            <div style="display:flex;gap:8px;font-size:11px">
                <span style="background:#E6F1FB;color:#0C447C;padding:2px 6px;border-radius:10px">
                    🏥 {specs} espec.
                </span>
                <span style="background:#EAF3DE;color:#27500A;padding:2px 6px;border-radius:10px">
                    {rating_html}
                </span>
            </div>
            <div style="margin-top:6px;font-size:12px;color:#185FA5;font-weight:500">
                Puntaje global: {score:.0f}
            </div>
        </div>
        """

        folium.CircleMarker(
            location=[lat, lng],
            radius=10,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"{i+1}. {nombre}",
        ).add_to(m)

        # Número sobre el pin
        folium.Marker(
            location=[lat, lng],
            icon=folium.DivIcon(
                html=f"""<div style="
                    font-size:10px;font-weight:700;color:#fff;
                    background:{color};border-radius:50%;
                    width:20px;height:20px;
                    display:flex;align-items:center;justify-content:center;
                    margin-left:-10px;margin-top:-10px;
                    box-shadow:0 1px 3px rgba(0,0,0,.3)
                ">{i+1}</div>""",
                icon_size=(20, 20),
                icon_anchor=(0, 0),
            ),
        ).add_to(m)

    st_folium(m, use_container_width=True, height=300, returned_objects=[])
