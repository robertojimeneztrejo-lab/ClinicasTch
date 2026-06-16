"""
components/ficha.py
Renderiza una ficha de resultado completa usando st.container + HTML.
"""

import streamlit as st


def _stars_html(rating: float) -> str:
    """Genera HTML de estrellas para un rating 0-5."""
    if rating is None:
        return ""
    full  = int(rating)
    half  = 1 if (rating - full) >= 0.25 else 0
    empty = 5 - full - half
    html  = "★" * full
    if half:
        html += "½"
    html += "☆" * empty
    return html


def _status_badge(abierto: bool | None, is_24h: bool | None) -> str:
    if abierto is None:
        return ""
    if abierto:
        label = "Abierto · 24h" if is_24h else "Abierto ahora"
        return f'<span style="background:#3B6D11;color:#EAF3DE;font-size:10px;padding:2px 8px;border-radius:20px;font-weight:500">● {label}</span>'
    return '<span style="background:#854F0B;color:#FAEEDA;font-size:10px;padding:2px 8px;border-radius:20px;font-weight:500">● Cerrado ahora</span>'


def _score_color(score: float) -> str:
    if score >= 85:
        return "#3B6D11"
    if score >= 70:
        return "#185FA5"
    return "#854F0B"


def render_ficha(org: dict, index: int, perfil_especialidades: list[str]):
    """
    Renderiza una ficha completa de organización.
    perfil_especialidades: lista de especialidades clave del perfil del estudiante.
    """
    places  = org.get("places", {})
    scores  = org.get("scores", {})
    jefe    = org.get("jefe_ensenanza", {}) or {}
    specs   = org.get("especialidades", [])
    score   = scores.get("score_global", 0)
    color   = _score_color(score)
    rating  = places.get("rating")
    foto    = places.get("foto_url")

    # Compatibles con el perfil
    perfil_lower = [e.lower() for e in perfil_especialidades]
    specs_compat = [s for s in specs if s.get("nombre", "").lower() in perfil_lower or s.get("compatible_perfil")]
    n_compat     = len(specs_compat)
    n_total      = len(specs)

    with st.container():
        # ── Hero / cabecera ──────────────────────────────────────────
        if foto:
            st.markdown(
                f"""<div style="
                    background:url('{foto}') center/cover no-repeat;
                    height:80px;border-radius:12px 12px 0 0;
                    position:relative;margin-bottom:0
                "><div style="
                    position:absolute;inset:0;border-radius:12px 12px 0 0;
                    background:linear-gradient(to right,rgba(0,0,0,.55),rgba(0,0,0,.1));
                    display:flex;align-items:flex-end;justify-content:space-between;
                    padding:.6rem 1rem
                ">
                    <span style="color:#fff;font-size:13px;font-weight:500;max-width:70%">
                        {index}. {org.get('nombre','')}
                    </span>
                    {_status_badge(places.get('abierto_ahora'), places.get('horario_24h'))}
                </div></div>""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""<div style="
                    background:linear-gradient(135deg,#B5D4F4,#9FE1CB);
                    height:80px;border-radius:12px 12px 0 0;
                    display:flex;align-items:flex-end;justify-content:space-between;
                    padding:.6rem 1rem
                ">
                    <span style="color:#fff;font-size:13px;font-weight:500">
                        {index}. {org.get('nombre','')}
                    </span>
                    {_status_badge(places.get('abierto_ahora'), places.get('horario_24h'))}
                </div>""",
                unsafe_allow_html=True,
            )

        # ── Cuerpo ───────────────────────────────────────────────────
        with st.container():
            st.markdown(
                f"""<div style="
                    border:0.5px solid var(--border);
                    border-top:none;border-radius:0 0 12px 12px;
                    padding:1rem 1.25rem;
                    background:var(--background-color)
                ">""",
                unsafe_allow_html=True,
            )

            # Meta + score
            col_info, col_score = st.columns([5, 1])
            with col_info:
                tipo  = org.get("tipo_institucion", "").replace("_", " ").title()
                pais  = org.get("pais", "")
                ciudad= org.get("ciudad", "")
                st.caption(f"🏥 {tipo} · {pais}  ·  📍 {ciudad}")

            with col_score:
                st.markdown(
                    f"""<div style="
                        width:46px;height:46px;border-radius:50%;
                        border:2px solid {color};
                        display:flex;flex-direction:column;
                        align-items:center;justify-content:center;
                        float:right
                    ">
                        <span style="font-size:14px;font-weight:500;color:{color};line-height:1">{score:.0f}</span>
                        <span style="font-size:9px;color:#888;line-height:1;margin-top:1px">global</span>
                    </div>""",
                    unsafe_allow_html=True,
                )

            # Badge especialidades
            st.markdown(
                f'<span style="background:#E6F1FB;color:#0C447C;font-size:11px;'
                f'padding:2px 8px;border-radius:20px;font-weight:500">'
                f'🩺 {n_total} especialidades · {n_compat} compatibles con tu perfil</span>',
                unsafe_allow_html=True,
            )
            st.markdown("<div style='margin:.4rem 0'></div>", unsafe_allow_html=True)

            # ── Columnas: Contacto | Google Maps + Modalidades ──────
            col_left, col_right = st.columns(2)

            with col_left:
                st.markdown(
                    "<p style='font-size:10px;font-weight:500;color:#888;"
                    "text-transform:uppercase;letter-spacing:.05em;margin-bottom:.3rem'>Contacto</p>",
                    unsafe_allow_html=True,
                )
                tel   = org.get("contacto_telefono") or places.get("telefono_places")
                email = org.get("contacto_email")
                web   = org.get("sitio_web") or places.get("web_places")
                dir_  = org.get("direccion") or places.get("direccion_places")

                items = [
                    ("📞", tel   or "_No verificado_"),
                    ("✉️", email  or "_No verificado_"),
                    ("🌐", f"[{web}]({web})" if web else "_No verificado_"),
                    ("📍", dir_  or "_No verificado_"),
                ]
                for icon, val in items:
                    st.markdown(f"{icon} {val}", unsafe_allow_html=False)

                # Jefe de enseñanza
                st.markdown("---")
                st.markdown(
                    "<p style='font-size:10px;font-weight:500;color:#888;"
                    "text-transform:uppercase;letter-spacing:.05em;margin-bottom:.3rem'>Jefe de enseñanza</p>",
                    unsafe_allow_html=True,
                )
                if jefe.get("nombre"):
                    verificado = jefe.get("verificado", False)
                    fecha      = jefe.get("fecha_verificacion", "")
                    chip_color = "#EAF3DE" if verificado else "#FAEEDA"
                    chip_text  = "#27500A" if verificado else "#633806"
                    chip_label = f"✓ Verificado {fecha}" if verificado else "⚠ Pendiente de verificar"
                    st.markdown(
                        f"""👤 **{jefe['nombre']}**
{jefe.get('cargo', '')}
<span style="background:{chip_color};color:{chip_text};font-size:9.5px;
padding:1px 6px;border-radius:20px">{chip_label}</span>""",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("_No encontrado_")

            with col_right:
                # Rating Google
                if rating is not None:
                    st.markdown(
                        "<p style='font-size:10px;font-weight:500;color:#888;"
                        "text-transform:uppercase;letter-spacing:.05em;margin-bottom:.3rem'>Google Maps</p>",
                        unsafe_allow_html=True,
                    )
                    num_r = places.get("num_resenas", 0)
                    maps_url = places.get("maps_url", "#")
                    st.markdown(
                        f"""<div style="background:var(--secondary-background-color);
                            border-radius:8px;padding:.6rem .75rem;margin-bottom:.5rem">
                            <div style="display:flex;align-items:center;gap:8px">
                                <span style="font-size:22px;font-weight:500">{rating}</span>
                                <div>
                                    <div style="color:#BA7517;font-size:14px">{_stars_html(rating)}</div>
                                    <div style="font-size:11px;color:#888">{num_r:,} reseñas</div>
                                </div>
                            </div>
                            <div style="font-size:10px;color:#888;margin-top:4px">
                                Google Places API · actualizado hoy
                            </div>
                            <a href="{maps_url}" target="_blank"
                               style="font-size:10px;color:#185FA5;text-decoration:none">
                               🗺 Ver perfil en Google Maps
                            </a>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                    # Menciones estudiantiles
                    menciones = places.get("menciones_estudiantiles", [])
                    if menciones:
                        st.markdown(
                            "<p style='font-size:10px;font-weight:500;color:#888;"
                            "text-transform:uppercase;letter-spacing:.05em;margin-bottom:.3rem'>"
                            "Menciones estudiantiles</p>",
                            unsafe_allow_html=True,
                        )
                        for m in menciones[:2]:
                            tag   = m.get("tag", "")
                            texto = m.get("texto", "")
                            st.markdown(
                                f"""<div style="background:var(--secondary-background-color);
                                    border-radius:8px;padding:.4rem .6rem;margin-bottom:.35rem;
                                    font-size:11px;color:#555">
                                    <span style="background:#EAF3DE;color:#27500A;font-size:9.5px;
                                    padding:1px 6px;border-radius:20px;margin-bottom:3px;
                                    display:inline-block">✓ {tag}</span><br>
                                    "{texto}"
                                </div>""",
                                unsafe_allow_html=True,
                            )

                # Modalidades
                modalidades = org.get("modalidades_aplicables", [])
                if modalidades:
                    st.markdown(
                        "<p style='font-size:10px;font-weight:500;color:#888;"
                        "text-transform:uppercase;letter-spacing:.05em;margin:.4rem 0 .3rem'>Modalidades</p>",
                        unsafe_allow_html=True,
                    )
                    tags_html = "".join(
                        f'<span style="font-size:10.5px;padding:2px 7px;border-radius:20px;'
                        f'background:{"#E6F1FB" if any(c in m for c in ["clinical","observ"]) else "var(--secondary-background-color)"};'
                        f'color:{"#0C447C" if any(c in m for c in ["clinical","observ"]) else "#666"};'
                        f'margin:2px">{m}</span>'
                        for m in modalidades
                    )
                    st.markdown(
                        f'<div style="display:flex;flex-wrap:wrap;gap:3px">{tags_html}</div>',
                        unsafe_allow_html=True,
                    )

            # ── Especialidades expandibles ──────────────────────────
            st.markdown("<div style='margin:.3rem 0'></div>", unsafe_allow_html=True)
            with st.expander(
                f"🩺 Especialidades disponibles — {n_total} en total · {n_compat} compatibles con tu perfil"
            ):
                if specs:
                    st.markdown(
                        '<div style="display:flex;gap:12px;font-size:10.5px;color:#888;margin-bottom:.5rem">'
                        '<span>🟢 Compatible con tu perfil</span>'
                        '<span>⚪ Otras especialidades</span>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                    chips = ""
                    for s in specs:
                        nombre_s = s.get("nombre", "")
                        compat   = s.get("compatible_perfil", False) or nombre_s.lower() in perfil_lower
                        bg    = "#EAF3DE" if compat else "var(--secondary-background-color)"
                        color_s = "#27500A" if compat else "#666"
                        border  = "#9FE1CB" if compat else "transparent"
                        chips += (
                            f'<span style="font-size:11px;padding:3px 9px;border-radius:20px;'
                            f'background:{bg};color:{color_s};border:0.5px solid {border};'
                            f'display:inline-block;margin:2px">{nombre_s}</span>'
                        )
                    st.markdown(
                        f'<div style="display:flex;flex-wrap:wrap;gap:2px">{chips}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("Sin especialidades registradas.")

            # ── Justificación ───────────────────────────────────────
            justif = org.get("justificacion", "")
            if justif:
                st.markdown(
                    f'<p style="font-size:11.5px;color:#666;line-height:1.6;margin:.4rem 0">{justif}</p>',
                    unsafe_allow_html=True,
                )

            # ── Botones pie ─────────────────────────────────────────
            st.markdown("---")
            c1, c2, c3, _ = st.columns([1, 1, 1, 3])
            maps_url_btn = places.get("maps_url") or (
                f"https://www.google.com/maps/search/{org.get('nombre','')}+{org.get('ciudad','')}"
            )
            with c1:
                st.link_button("📍 Ver en mapa", maps_url_btn, use_container_width=True)
            with c2:
                web_btn = org.get("sitio_web") or places.get("web_places") or "#"
                st.link_button("🌐 Sitio web", web_btn, use_container_width=True)
            with c3:
                # La descarga de ficha se maneja desde app.py
                st.session_state[f"download_{org.get('nombre','')}"] = org

            st.markdown("</div>", unsafe_allow_html=True)
