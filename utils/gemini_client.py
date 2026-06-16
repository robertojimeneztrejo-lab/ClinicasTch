"""
utils/gemini_client.py
Llama a Gemini 2.5 Flash con el prompt estructurado y retorna JSON validado.
"""

import json
import re
import streamlit as st
import google.generativeai as genai

genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
_MODEL = "gemini-2.5-flash"


def _clean_json(text: str) -> str:
    """
    Extrae el JSON de la respuesta de Gemini, incluso cuando viene rodeado
    de texto explicativo o citas de búsqueda (común cuando grounding está
    activo). Estrategia: quitar fences markdown, luego recortar al primer
    '{' y al último '}' del texto.
    """
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    first = text.find("{")
    last  = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        text = text[first:last + 1]

    return text.strip()


def _build_prompt(dossier_text: str, filters: dict) -> str:
    regions     = ", ".join(filters.get("regions", ["México"]))
    location    = filters.get("location", "Ciudad de México")
    radius_km   = filters.get("radius_km", 50)
    modalities  = " | ".join(filters.get("modalities", []))
    inst_types  = " | ".join(filters.get("inst_types", []))
    max_results = filters.get("max_results", 15)
    min_specs   = filters.get("min_specs", 1)

    return f"""
Actúa como especialista en vinculación universitaria, desarrollo académico y análisis geoespacial.

CONTEXTO DE BÚSQUEDA:
- Regiones objetivo: {regions}
- Ubicación de referencia: {location} (radio: {radius_km} km)
- Máximo de resultados: {max_results}
- Tipos de institución aceptados: {inst_types}
- Modalidades requeridas: {modalities}
- Mínimo de especialidades: {min_specs}

---

FASE 1 — PERFIL DE INSERCIÓN PROFESIONAL
Analiza el siguiente dossier académico e identifica:

{dossier_text}

Extrae en el JSON final:
- competencias_profesionales (lista)
- competencias_tecnicas (lista)
- competencias_clinicas (lista)
- procesos_a_ejecutar (lista)
- sectores_economicos (lista)
- infraestructura_requerida (lista)
- entornos_laborales (lista)
- resumen_perfil (máximo 300 palabras)
- especialidades_clave (lista de especialidades médicas/clínicas centrales del perfil,
  usadas para marcar compatibilidad en cada organización)

---

FASE 2 — MODALIDADES APLICABLES
Selecciona del siguiente listado SOLO las que aplican al programa del dossier:

CATEGORÍA A — Prácticas clínicas formales:
prácticas_clínicas | campos_clínicos | rotaciones_clínicas | internado |
servicio_social | estancias_clínicas | rotaciones_hospitalarias

CATEGORÍA B — Formación supervisada:
pasantías | concurrencias | residencias_observacionales | observerships |
formación_en_servicio | concurrente

CATEGORÍA C — Acuerdos institucionales:
convenios_docencia_servicio | prácticas_asistenciales | prácticum |
prácticas_curriculares | estancias_formativas | convenio_universitario |
escenarios_de_práctica

CATEGORÍA D — Terminología internacional (EN):
clinical_placement | clinical_training | observership | clinical_rotation

---

FASE 3 — ORGANIZACIONES CANDIDATAS
Busca hasta {max_results} organizaciones en las regiones indicadas compatibles con
el perfil. Usa tu conocimiento actualizado y web search para fundamentar.

Para cada organización devuelve EXACTAMENTE este JSON:
{{
  "id": "secuencial",
  "nombre": "",
  "tipo_institucion": "hospital_publico|hospital_privado|hospital_universitario|instituto_nacional|clinica_policlinico|atencion_primaria|salud_comunitaria|clinica_universitaria|imss_issste|sanatorio|investigacion_clinica",
  "especialidad_principal": "",
  "especialidades": [
    {{
      "nombre": "",
      "compatible_perfil": true
    }}
  ],
  "modalidades_aplicables": [],
  "direccion": "",
  "ciudad": "",
  "estado": "",
  "pais": "",
  "coordenadas": {{ "lat": null, "lng": null }},
  "contacto_telefono": "",
  "contacto_email": "",
  "sitio_web": "",
  "jefe_ensenanza": {{
    "nombre": null,
    "cargo": null,
    "verificado": false,
    "fecha_verificacion": null
  }},
  "horario_atencion": null,
  "scores": {{
    "compatibilidad_academica": 0,
    "capacidad_formativa": 0,
    "infraestructura": 0,
    "prestigio": 0,
    "investigacion": 0,
    "potencial_convenio": 0,
    "score_global": 0
  }},
  "justificacion": "",
  "fuente": ""
}}

IMPORTANTE — instrucciones de búsqueda de contacto (usa Google Search real,
no recuerdes de memoria):
- Para CADA organización, usa la herramienta de búsqueda para encontrar su
  sitio web OFICIAL real. Verifica el dominio exacto letra por letra —
  NUNCA infieras o adivines un dominio por similitud de nombre. Por ejemplo,
  un instituto llamado "X de la Ciudad de México" puede tener dominio
  "xcdmx.gob.mx", NO necesariamente "x.gob.mx". Si tienes cualquier duda
  sobre el dominio exacto, busca explícitamente "[nombre institución] sitio
  oficial" y usa solo la URL que aparezca en los resultados de búsqueda reales.
- sitio_web: debe ser la URL exacta encontrada en la búsqueda, copiada tal
  cual aparece en los resultados. Si no la encuentras con certeza, usa null
  en vez de adivinar — un campo null es preferible a un link roto.
- contacto_email: busca en la página de "Contacto" del sitio oficial real
  (ya verificado). Patrones comunes: "contacto@", "oficialia@",
  "enseñanza@", "docencia@".
- jefe_ensenanza.nombre: busca en "Quiénes somos" o "Directorio" del sitio
  oficial real el cargo "Director", "Subdirector de Enseñanza", "Jefe de
  Enseñanza e Investigación" o "Coordinador de Docencia". Si solo hay
  Director General, úsalo con cargo "Director General".
- horario_atencion: extrae el horario EXACTO como está escrito en la página
  de contacto del sitio oficial (ej: "Lunes a Viernes 09:00 a 17:00 hrs").
  Esto es más confiable que el horario de Google Maps. Si no está publicado,
  usa null.
- Solo devuelve null si después de buscar realmente el dato no está
  publicado. Nunca inventes ni infieras contactos, dominios o horarios.
- score_global = (compatibilidad_academica×0.35) + (capacidad_formativa×0.25)
  + (infraestructura×0.15) + (prestigio×0.10) + (investigacion×0.10)
  + (potencial_convenio×0.05)
- Devuelve al menos {min_specs} especialidades por organización.
- Ordena el array por score_global descendente.

---

FORMATO FINAL — responde ÚNICAMENTE con este JSON válido, sin texto adicional,
sin bloques markdown:

{{
  "perfil": {{
    "competencias_profesionales": [],
    "competencias_tecnicas": [],
    "competencias_clinicas": [],
    "procesos_a_ejecutar": [],
    "sectores_economicos": [],
    "infraestructura_requerida": [],
    "entornos_laborales": [],
    "resumen_perfil": "",
    "especialidades_clave": []
  }},
  "modalidades": {{
    "categoria_a": [],
    "categoria_b": [],
    "categoria_c": [],
    "categoria_d": []
  }},
  "organizaciones": [],
  "metadata": {{
    "total_encontradas": 0,
    "regiones": [],
    "ubicacion_referencia": "",
    "radio_km": 0
  }}
}}
""".strip()


def analyze_dossier(dossier_text: str, filters: dict) -> dict:
    """
    Llama a Gemini CON Google Search grounding y retorna el dict con
    perfil + organizaciones. Lanza ValueError si el JSON es inválido.

    NOTA: grounding (tools=google_search) y response_mime_type=json no son
    compatibles simultáneamente en la API de Gemini, por eso forzamos el
    formato JSON solo mediante instrucciones explícitas en el prompt y
    parseo robusto, en vez de mediante response_mime_type.
    """
    prompt = _build_prompt(dossier_text, filters)
    model  = genai.GenerativeModel(_MODEL)

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.2,
            max_output_tokens=65536,
        ),
        tools="google_search",
    )

    finish_reason = None
    try:
        finish_reason = response.candidates[0].finish_reason.name
    except Exception:
        pass

    raw   = response.text
    clean = _clean_json(raw)

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        data = None
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                data = None

        if data is None:
            truncated_msg = (
                " (la respuesta se cortó por límite de tokens — "
                "reduce el numero de resultados maximos o sube el limite)"
                if finish_reason == "MAX_TOKENS" else ""
            )
            raise ValueError(
                f"Gemini no devolvio JSON valido{truncated_msg}.\n"
                f"finish_reason={finish_reason}\n"
                f"Primeros 300 caracteres: {raw[:300]}\n"
                f"Ultimos 300 caracteres: {raw[-300:]}"
            )

    return data
