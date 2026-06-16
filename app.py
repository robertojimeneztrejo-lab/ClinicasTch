"""
app.py — Clinical Finder
Buscador de campos de práctica con Gemini + Google Places + Supabase.
Funciona para CUALQUIER facultad: medicina, derecho, psicología, ingeniería,
trabajo social, etc. — el tipo de institución y la modalidad se infieren
automáticamente del dossier, no se eligen de una lista fija.
"""

import json
import streamlit as st
import PyPDF2
import io

from utils.gemini_client    import analyze_dossier
from utils.places_client    import enrich_all
from utils.geocoding        import geocode_location
from utils.supabase_client  import save_search, save_results, load_history, load_search_results
from components.mapa        import render_map
from components.ficha       import render_ficha

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Buscador de Campos de Práctica",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS global ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] { min-width: 280px; max-width: 300px; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
div[data-testid="stExpander"] { border: 0.5px solid rgba(0,0,0,.1); border-radius: 8px; }
hr { margin: .5rem 0; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────
def extract_pdf_text(uploaded_file) -> str:
    """Extrae texto de un PDF subido."""
    reader = PyPDF2.PdfReader(io.BytesIO(uploaded_file.read()))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


def sort_orgs(orgs: list, criterio: str) -> list:
    if criterio == "Puntaje global ↓":
        return sorted(orgs, key=lambda o: o.get("scores", {}).get("score_global", 0), reverse=True)
    if criterio == "Del más cercano al más lejano":
        return sorted(orgs, key=lambda o: o.get("distancia_km_aproximada", 9999))
    if criterio == "Del más lejano al más cercano":
        return sorted(orgs, key=lambda o: o.get("distancia_km_aproximada", 0), reverse=True)
    if criterio == "Mayor número de especialidades":
        return sorted(orgs, key=lambda o: len(o.get("especialidades", [])), reverse=True)
    return orgs


def org_to_json_download(org: dict) -> str:
    return json.dumps(org, ensure_ascii=False, indent=2)


# ── Estado de sesión ─────────────────────────────────────────────────────────
defaults = {
    "results":          [],
    "perfil":           {},
    "tipos_dinamicos":  [],
    "modalidades_dinamicas": [],
    "searching":        False,
    "dossier_text":     "",
    "last_radius_km":   3,
    "last_location":    "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🎓 Buscador de Campos de Práctica")
    st.caption("Para cualquier facultad — la IA define tipo de institución y modalidad")
    st.divider()

    # ── Dossier ─────────────────────────────────────────────────────────────
    st.markdown("**📄 Dossier académico**")
    uploaded = st.file_uploader(
        "Sube el dossier (PDF)",
        type=["pdf"],
        label_visibility="collapsed",
    )
    if uploaded:
        with st.spinner("Leyendo PDF…"):
            st.session_state.dossier_text = extract_pdf_text(uploaded)
        st.success(f"✅ {uploaded.name} · {len(st.session_state.dossier_text):,} caracteres")

    if st.session_state.perfil.get("resumen_perfil"):
        with st.expander("👤 Perfil generado"):
            p = st.session_state.perfil
            if p.get("facultad_o_programa"):
                st.markdown(f"**Facultad/Programa:** {p['facultad_o_programa']}")
            st.caption(p.get("resumen_perfil", ""))
            if p.get("areas_clave"):
                st.markdown("**Áreas clave:**")
                st.write(", ".join(p["areas_clave"]))

    st.divider()

    # ── Ubicación simplificada: referencia + país ──────────────────────────
    st.markdown("**📍 Ubicación**")
    location = st.text_input(
        "Referencia (colonia, zona, dirección o ciudad)",
        value=st.session_state.last_location or "Polanco",
        help="Sé tan específico como puedas: una colonia o dirección da resultados "
             "más precisos que solo el nombre de la ciudad.",
    )
    pais = st.text_input("País", value="México")

    radius_km = st.slider(
        "Radio de búsqueda (km)",
        min_value=1, max_value=5, value=3, step=1,
        help="La distancia se calcula desde coordenadas exactas, geocodificadas "
             "a partir de tu referencia + país.",
    )

    st.divider()

    # ── Filtros numéricos ────────────────────────────────────────────────────
    st.markdown("**🔢 Filtros numéricos**")
    min_specs   = st.slider("Mínimo de especialidades/áreas por institución", 1, 30, 3)
    max_results = st.select_slider(
        "Tope máximo de resultados",
        options=[10, 20, 30, 40, 50],
        value=50,
        help="No es una meta — la IA devuelve todas las instituciones válidas "
             "encontradas en el radio, hasta este techo de seguridad.",
    )

    st.divider()

    # ── Botón de búsqueda ────────────────────────────────────────────────────
    search_disabled = not st.session_state.dossier_text
    if st.button(
        "🔍 Buscar organizaciones",
        type="primary",
        use_container_width=True,
        disabled=search_disabled,
    ):
        st.session_state.searching = True

    if search_disabled:
        st.caption("⬆ Sube un dossier PDF para habilitar la búsqueda.")

    st.divider()

    # ── Filtros sobre resultados ya obtenidos (post-búsqueda) ────────────────
    # Aparecen solo si ya hay resultados, y se llenan con lo que Gemini generó
    # dinámicamente — nunca con una lista fija predefinida.
    if st.session_state.tipos_dinamicos or st.session_state.modalidades_dinamicas:
        st.markdown("**🔧 Filtrar resultados actuales**")

        if st.session_state.tipos_dinamicos:
            tipo_labels = {t["valor"]: t["label"] for t in st.session_state.tipos_dinamicos}
            tipos_filtro = st.multiselect(
                "Tipo de institución (detectado por la IA)",
                options=list(tipo_labels.keys()),
                default=list(tipo_labels.keys()),
                format_func=lambda v: tipo_labels.get(v, v),
            )
        else:
            tipos_filtro = None

        if st.session_state.modalidades_dinamicas:
            modal_filtro = st.multiselect(
                "Modalidad (detectada por la IA)",
                options=st.session_state.modalidades_dinamicas,
                default=st.session_state.modalidades_dinamicas,
            )
        else:
            modal_filtro = None

        st.divider()
    else:
        tipos_filtro = None
        modal_filtro = None

    # ── Historial ────────────────────────────────────────────────────────────
    st.markdown("**🕑 Historial de búsquedas**")
    try:
        history = load_history(limit=10)
        if history:
            for h in history:
                fecha  = h["created_at"][:10]
                label  = f"{fecha} · {h.get('location','')}"
                if st.button(label, key=f"hist_{h['id']}", use_container_width=True):
                    with st.spinner("Cargando resultados guardados…"):
                        rows = load_search_results(h["id"])
                        st.session_state.results = [r["raw_json"] for r in rows if r.get("raw_json")]
        else:
            st.caption("Sin búsquedas guardadas aún.")
    except Exception:
        st.caption("Historial no disponible.")


# ════════════════════════════════════════════════════════════════════════════
# BÚSQUEDA PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════
if st.session_state.searching:
    st.session_state.searching = False
    st.session_state.last_location = location
    st.session_state.last_radius_km = radius_km

    # Paso 1: Geocodificar la referencia a coordenadas exactas
    with st.spinner("📍 Localizando referencia geográfica…"):
        geo = geocode_location(location, pais)

    if not geo["encontrado"]:
        st.warning(
            f"No se pudo geocodificar '{location}, {pais}' "
            f"({geo.get('error', 'motivo desconocido')}). "
            f"La búsqueda continuará usando solo el texto de referencia, "
            f"sin radio exacto calculado."
        )

    filters = {
        "location":    geo.get("direccion_formateada") or location,
        "pais":        pais,
        "radius_km":   radius_km,
        "lat":         geo.get("lat"),
        "lng":         geo.get("lng"),
        "min_specs":   min_specs,
        "max_results": max_results,
    }

    with st.spinner("🤖 Gemini analizando el dossier y buscando organizaciones…"):
        try:
            data = analyze_dossier(st.session_state.dossier_text, filters)
            st.session_state.perfil = data.get("perfil", {})
            st.session_state.tipos_dinamicos = data.get("tipos_institucion_relevantes", [])
            st.session_state.modalidades_dinamicas = data.get("modalidades_relevantes", [])
            orgs = data.get("organizaciones", [])
        except Exception as e:
            st.error(f"Error en Gemini: {e}")
            st.stop()

    with st.spinner(f"🗺 Enriqueciendo {len(orgs)} organizaciones con Google Places API…"):
        orgs = enrich_all(orgs)
        st.session_state.results = orgs

    with st.spinner("💾 Guardando en Supabase…"):
        try:
            search_id = save_search(filters, st.session_state.perfil)
            save_results(search_id, orgs)
        except Exception as e:
            st.warning(f"No se pudo guardar en Supabase: {e}")

    st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# RESULTADOS
# ════════════════════════════════════════════════════════════════════════════
orgs = st.session_state.results

if not orgs:
    st.markdown("## 🎓 Buscador de Campos de Práctica")
    st.info(
        "Sube un dossier académico en el panel izquierdo y haz clic en "
        "**Buscar organizaciones** para comenzar. Funciona para cualquier "
        "facultad — la IA detecta automáticamente qué tipo de institución "
        "y modalidad de práctica corresponden a tu programa."
    )
    st.stop()

# ── Aplicar filtros dinámicos post-búsqueda (no vuelven a llamar a Gemini) ───
orgs_filtrados = orgs
if tipos_filtro is not None:
    orgs_filtrados = [o for o in orgs_filtrados if o.get("tipo_institucion") in tipos_filtro]
if modal_filtro is not None:
    orgs_filtrados = [
        o for o in orgs_filtrados
        if any(m in (o.get("modalidades_aplicables") or []) for m in modal_filtro)
    ]

# ── Top bar ──────────────────────────────────────────────────────────────────
col_title, col_s1, col_s2, col_s3 = st.columns([4, 1, 1, 1])
with col_title:
    st.markdown("## 🎓 Buscador de Campos de Práctica")
with col_s1:
    st.metric("Resultados", len(orgs_filtrados))
with col_s2:
    st.metric("Radio activo", f"{st.session_state.last_radius_km} km")
with col_s3:
    n_tipos = len(set(o.get("tipo_institucion") for o in orgs_filtrados))
    st.metric("Tipos de institución", n_tipos)

# ── Mapa ─────────────────────────────────────────────────────────────────────
render_map(orgs_filtrados)

# ── Controles de resultados ──────────────────────────────────────────────────
orden = st.selectbox(
    "Ordenar por",
    ["Puntaje global ↓", "Del más cercano al más lejano",
     "Del más lejano al más cercano", "Mayor número de especialidades"],
)

orgs_sorted  = sort_orgs(orgs_filtrados, orden)
perfil_areas = st.session_state.perfil.get("areas_clave", [])

st.markdown(
    f"**Fichas de resultado** ({len(orgs_sorted)} de {len(orgs)} totales "
    f"— filtros aplicados en el sidebar)"
    if len(orgs_sorted) != len(orgs) else
    f"**Fichas de resultado** ({len(orgs_sorted)})"
)
st.divider()

# ── Fichas ───────────────────────────────────────────────────────────────────
for i, org in enumerate(orgs_sorted, start=1):
    render_ficha(org, i, perfil_areas)

    nombre = org.get("nombre", f"org_{i}")
    st.download_button(
        label="⬇ Descargar esta ficha (JSON)",
        data=org_to_json_download(org),
        file_name=f"{nombre[:40].replace(' ','_')}.json",
        mime="application/json",
        key=f"dl_{i}_{nombre[:10]}",
    )
    st.divider()
