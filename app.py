"""
app.py — Clinical Finder
Buscador de campos clínicos con Gemini + Google Places + Supabase
"""

import json
import streamlit as st
import PyPDF2
import io

from utils.gemini_client  import analyze_dossier
from utils.places_client  import enrich_all
from utils.supabase_client import save_search, save_results, load_history, load_search_results
from components.mapa      import render_map
from components.ficha     import render_ficha

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Buscador de Campos Clínicos",
    page_icon="🏥",
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


def sort_orgs(orgs: list[dict], criterio: str) -> list[dict]:
    if criterio == "Puntaje global ↓":
        return sorted(orgs, key=lambda o: o.get("scores", {}).get("score_global", 0), reverse=True)
    if criterio == "Del más cercano al más lejano":
        return sorted(orgs, key=lambda o: o.get("_distancia_km", 9999))
    if criterio == "Del más lejano al más cercano":
        return sorted(orgs, key=lambda o: o.get("_distancia_km", 0), reverse=True)
    if criterio == "Mayor número de especialidades":
        return sorted(orgs, key=lambda o: len(o.get("especialidades", [])), reverse=True)
    return orgs


def org_to_json_download(org: dict) -> str:
    return json.dumps(org, ensure_ascii=False, indent=2)


# ── Estado de sesión ─────────────────────────────────────────────────────────
if "results"       not in st.session_state: st.session_state.results       = []
if "perfil"        not in st.session_state: st.session_state.perfil        = {}
if "modalidades"   not in st.session_state: st.session_state.modalidades   = {}
if "searching"     not in st.session_state: st.session_state.searching     = False
if "dossier_text"  not in st.session_state: st.session_state.dossier_text  = ""


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🏥 Clinical Finder")
    st.caption("Buscador de campos clínicos con IA")
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
            st.caption(p.get("resumen_perfil", ""))
            if p.get("especialidades_clave"):
                st.markdown("**Especialidades clave:**")
                st.write(", ".join(p["especialidades_clave"]))

    st.divider()

    # ── Región ──────────────────────────────────────────────────────────────
    st.markdown("**🌎 Región de búsqueda**")
    regiones_opts = ["México", "España", "Argentina", "Colombia"]
    regiones = st.multiselect(
        "Regiones",
        options=regiones_opts,
        default=regiones_opts,
        label_visibility="collapsed",
    )

    st.markdown("**📍 Ubicación de referencia**")
    col_loc, col_btn = st.columns([4, 1])
    with col_loc:
        location = st.text_input("Ciudad", value="Ciudad de México", label_visibility="collapsed")
    with col_btn:
        st.button("📡", help="Usar mi ubicación actual (próximamente)", disabled=True)

    radius_km = st.slider("Radio de búsqueda (km)", 5, 200, 50, step=5)

    st.divider()

    # ── Tipo de institución ──────────────────────────────────────────────────
    st.markdown("**🏛 Tipo de institución**")
    INST_OPTS = {
        "Hospital público / General":    "hospital_publico",
        "Hospital privado":              "hospital_privado",
        "Hospital universitario":        "hospital_universitario",
        "Instituto nacional de salud":   "instituto_nacional",
        "Clínica / Policlínico":         "clinica_policlinico",
        "Centro de atención primaria":   "atencion_primaria",
        "Centro de salud comunitario":   "salud_comunitaria",
        "Clínica universitaria":         "clinica_universitaria",
        "IMSS / ISSSTE / Seg. social":   "imss_issste",
        "Sanatorio / Clínica especializada": "sanatorio",
        "Centro de investigación clínica":   "investigacion_clinica",
    }
    inst_selected = []
    for label, val in INST_OPTS.items():
        default = val in ["hospital_publico", "hospital_privado", "hospital_universitario", "instituto_nacional"]
        if st.checkbox(label, value=default, key=f"inst_{val}"):
            inst_selected.append(val)

    st.divider()

    # ── Modalidades ──────────────────────────────────────────────────────────
    st.markdown("**📋 Modalidad (ES / EN)**")
    MODAL_OPTS = [
        "Prácticas clínicas", "Campos clínicos", "Rotaciones clínicas",
        "Internado", "Servicio social", "Pasantías", "Concurrencias",
        "Escenarios de práctica", "Docencia-servicio", "Prácticum",
        "Prácticas curriculares", "Convenio universitario",
        "Clinical placement", "Clinical training", "Observership",
    ]
    EN_TERMS = {"Clinical placement", "Clinical training", "Observership"}
    DEFAULT_MODAL = {"Prácticas clínicas", "Campos clínicos", "Rotaciones clínicas", "Internado", "Servicio social"}

    modal_selected = []
    for m in MODAL_OPTS:
        label = f"🔵 {m}" if m in EN_TERMS else m
        if st.checkbox(label, value=(m in DEFAULT_MODAL), key=f"modal_{m}"):
            modal_selected.append(m)

    st.divider()

    # ── Filtros numéricos ────────────────────────────────────────────────────
    st.markdown("**🔢 Filtros numéricos**")
    min_specs   = st.slider("Mínimo de especialidades", 1, 30, 5)
    max_results = st.select_slider(
        "Cantidad de resultados",
        options=[5, 10, 15, 20, 25, 30],
        value=15,
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

    # ── Historial ────────────────────────────────────────────────────────────
    st.markdown("**🕑 Historial de búsquedas**")
    try:
        history = load_history(limit=10)
        if history:
            for h in history:
                fecha  = h["created_at"][:10]
                regs   = ", ".join(h.get("regions", []))
                label  = f"{fecha} · {h.get('location','')} · {regs}"
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

    filters = {
        "regions":      regiones,
        "location":     location,
        "radius_km":    radius_km,
        "modalities":   modal_selected,
        "inst_types":   inst_selected,
        "min_specs":    min_specs,
        "max_results":  max_results,
    }

    with st.spinner("🤖 Gemini analizando el dossier y buscando organizaciones…"):
        try:
            data = analyze_dossier(st.session_state.dossier_text, filters)
            st.session_state.perfil      = data.get("perfil", {})
            st.session_state.modalidades = data.get("modalidades", {})
            orgs = data.get("organizaciones", [])
        except Exception as e:
            st.error(f"Error en Gemini: {e}")
            st.stop()

    with st.spinner("🗺 Enriqueciendo con Google Places API…"):
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
    st.markdown("## 🏥 Buscador de Campos Clínicos")
    st.info("Sube un dossier académico en el panel izquierdo y haz clic en **Buscar organizaciones** para comenzar.")
    st.stop()

# ── Top bar ──────────────────────────────────────────────────────────────────
col_title, col_s1, col_s2, col_s3 = st.columns([4, 1, 1, 1])
with col_title:
    st.markdown("## 🏥 Buscador de Campos Clínicos")
with col_s1:
    st.metric("Resultados", len(orgs))
with col_s2:
    st.metric("Radio activo", f"{radius_km} km")
with col_s3:
    st.metric("Regiones", len(regiones))

# ── Mapa ─────────────────────────────────────────────────────────────────────
render_map(orgs)

# ── Controles de resultados ──────────────────────────────────────────────────
col_ord, col_dl = st.columns([3, 1])
with col_ord:
    orden = st.selectbox(
        "Ordenar por",
        ["Puntaje global ↓", "Del más cercano al más lejano",
         "Del más lejano al más cercano", "Mayor número de especialidades"],
        label_visibility="collapsed",
    )
with col_dl:
    all_json = json.dumps(orgs, ensure_ascii=False, indent=2)
    st.download_button(
        "⬇ Descargar todo (JSON)",
        data=all_json,
        file_name="campos_clinicos.json",
        mime="application/json",
        use_container_width=True,
    )

orgs_sorted = sort_orgs(orgs, orden)
perfil_specs = st.session_state.perfil.get("especialidades_clave", [])

st.markdown(f"**Fichas de resultado** ({len(orgs_sorted)})")
st.divider()

# ── Fichas ───────────────────────────────────────────────────────────────────
for i, org in enumerate(orgs_sorted, start=1):
    render_ficha(org, i, perfil_specs)

    # Botón de descarga individual por ficha
    nombre = org.get("nombre", f"org_{i}")
    st.download_button(
        label="⬇ Descargar esta ficha (JSON)",
        data=org_to_json_download(org),
        file_name=f"{nombre[:40].replace(' ','_')}.json",
        mime="application/json",
        key=f"dl_{i}_{nombre[:10]}",
    )
    st.divider()
