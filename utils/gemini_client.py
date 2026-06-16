"""
utils/gemini_client.py
Llama a Gemini 2.5 Flash con el prompt estructurado y retorna JSON validado.

Usa el SDK 'google-genai' (vigente), NO 'google-generativeai' (archivado por
Google el 16-dic-2025). Activa Google Search grounding para evitar que el
modelo alucine dominios web, contactos o directores por similitud de nombre.

DISEÑO MULTI-FACULTAD: el tipo de institución y la modalidad de práctica YA
NO se seleccionan de una lista fija en el sidebar. Gemini los infiere del
dossier en la Fase 2 (cualquier facultad: medicina, derecho, psicología,
ingeniería, etc.) y los asigna por organización en la Fase 3. El front-end
solo filtra/agrupa después de recibir la respuesta — ver utils/filters.py.
"""

import json
import re
import streamlit as st
from google import genai
from google.genai import types

_MODEL = "gemini-2.5-flash"

_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


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
    location    = filters.get("location", "")
    pais        = filters.get("pais", "")
    radius_km   = filters.get("radius_km", 3)
    lat         = filters.get("lat")
    lng         = filters.get("lng")
    max_results = filters.get("max_results", 50)
    min_specs   = filters.get("min_specs", 1)

    coords_line = (
        f"- Coordenadas exactas del centro de búsqueda: {lat}, {lng}"
        if lat is not None and lng is not None else
        "- Coordenadas exactas: no disponibles, usa el nombre de la ubicación tal cual"
    )

    return f"""
Actúa como especialista en vinculación universitaria, desarrollo académico y análisis geoespacial.
Tu tarea cubre estudiantes de CUALQUIER facultad o programa académico (medicina,
derecho, psicología, ingeniería, trabajo social, administración, etc.), no solo
ciencias de la salud. El tipo de institución y la modalidad de práctica deben
inferirse del dossier, NO asumas que es un perfil clínico a menos que el
dossier lo indique.

CONTEXTO DE BÚSQUEDA:
- Ubicación de referencia: {location}
- País: {pais}
{coords_line}
- Radio de búsqueda: {radius_km} km — SOLO incluye organizaciones dentro de
  este radio exacto desde el centro de búsqueda. Si no estás seguro de que
  una organización esté dentro del radio, exclúyela (mejor un resultado
  menos que uno fuera de rango).
- Máximo de resultados: {max_results} (úsalo como techo, no como meta — si
  hay menos organizaciones válidas en el radio, devuelve solo esas)
- Mínimo de especialidades/áreas por organización: {min_specs}

---

FASE 1 — PERFIL DE INSERCIÓN PROFESIONAL
Analiza el siguiente dossier académico e identifica a qué facultad o programa
pertenece, y extrae:

{dossier_text}

Extrae en el JSON final:
- facultad_o_programa (ej: "Medicina", "Derecho", "Psicología", "Ingeniería Civil")
- competencias_profesionales (lista)
- competencias_tecnicas (lista)
- competencias_especializadas (lista — equivalente a "clínicas" pero genérico
  para cualquier facultad: procesales para Derecho, terapéuticas para
  Psicología, de obra para Ingeniería, etc.)
- procesos_a_ejecutar (lista)
- sectores_economicos (lista)
- infraestructura_requerida (lista)
- entornos_laborales (lista)
- resumen_perfil (máximo 300 palabras)
- areas_clave (lista de áreas/especialidades centrales del perfil, usadas
  para marcar compatibilidad en cada organización — equivalente genérico a
  "especialidades_clave")

---

FASE 2 — TIPOS DE INSTITUCIÓN Y MODALIDADES (GENERADOS DINÁMICAMENTE)
Con base en la facultad/programa identificado, define TÚ MISMO:

a) tipos_institucion_relevantes: lista de 5-12 tipos de organización
   receptora adecuados para ESTE perfil específico. Ejemplos según facultad
   (NO uses esta lista literal, es solo referencia de qué tan específico
   debe ser):
   - Medicina/Enfermería → hospital público, hospital universitario, centro
     de salud, instituto nacional de salud
   - Derecho → juzgado, fiscalía, notaría, despacho jurídico, defensoría
     pública, comisión de derechos humanos
   - Psicología → centro de salud mental, clínica psicológica, DIF, centro
     de atención a víctimas, hospital psiquiátrico
   - Ingeniería Civil → constructora, despacho de proyectos, dependencia de
     obras públicas, empresa de infraestructura
   - Trabajo Social → DIF, ONG de asistencia social, centro comunitario,
     dependencia de desarrollo social
   Usa snake_case para cada tipo (ej: "juzgado_civil", "despacho_juridico").

b) modalidades_relevantes: lista de 5-15 términos de modalidad de práctica
   adecuados para ESTE perfil, en español y/o inglés si aplica terminología
   internacional. Ejemplos de referencia (adapta, no copies literal):
   - Medicina → prácticas clínicas, internado, servicio social, rotaciones,
     clinical placement, observership
   - Derecho → práctica jurídica, servicio social legal, pasantía profesional,
     prácticum jurídico
   - Ingeniería → prácticas profesionales, residencia profesional, servicio
     social, pasantía técnica

---

FASE 3 — ORGANIZACIONES CANDIDATAS
Busca organizaciones reales dentro del radio de {radius_km} km desde la
ubicación de referencia, compatibles con el perfil. Usa búsqueda real
(Google Search) para fundamentar cada dato — NUNCA inventes ni infieras por
similitud de nombre.

Para cada organización devuelve EXACTAMENTE este JSON:
{{
  "id": "secuencial",
  "nombre": "",
  "tipo_institucion": "snake_case definido en tipos_institucion_relevantes",
  "tipo_institucion_label": "Nombre legible del tipo (ej: 'Juzgado Civil')",
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
  "distancia_km_aproximada": 0,
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

IMPORTANTE — instrucciones de búsqueda y verificación (usa Google Search
real, no recuerdes de memoria):
- RADIO ESTRICTO: calcula o estima distancia_km_aproximada desde el centro
  de búsqueda. Si la organización está claramente fuera de {radius_km} km,
  NO la incluyas en el resultado.
- tipo_institucion: usa ÚNICAMENTE uno de los valores que tú mismo definiste
  en tipos_institucion_relevantes (Fase 2). Esto permite que el sistema
  agrupe resultados consistentemente.
- Para CADA organización, usa la herramienta de búsqueda para encontrar su
  sitio web OFICIAL real. Verifica el dominio exacto letra por letra —
  NUNCA infieras o adivines un dominio por similitud de nombre. Si tienes
  cualquier duda sobre el dominio exacto, busca explícitamente "[nombre
  institución] sitio oficial" y usa solo la URL que aparezca en los
  resultados de búsqueda reales.
- sitio_web: debe ser la URL exacta encontrada en la búsqueda. Si no la
  encuentras con certeza, usa null — un campo null es preferible a un link
  roto.
- contacto_email: busca en la página de "Contacto" del sitio oficial real
  ya verificado.
- jefe_ensenanza.nombre: busca el responsable de vinculación, prácticas o
  servicio social en "Quiénes somos" o "Directorio" del sitio oficial. Si
  solo hay un Director General, úsalo con el cargo correspondiente.
- horario_atencion: extrae el horario EXACTO como está escrito en la página
  de contacto del sitio oficial (ej: "Lunes a Viernes 09:00 a 17:00 hrs").
  Si no está publicado, usa null.
- Solo devuelve null si después de buscar realmente el dato no está
  publicado. Nunca inventes ni infieras contactos, dominios, horarios o
  distancias.
- score_global = (compatibilidad_academica×0.35) + (capacidad_formativa×0.25)
  + (infraestructura×0.15) + (prestigio×0.10) + (investigacion×0.10)
  + (potencial_convenio×0.05)
- Devuelve al menos {min_specs} especialidades/áreas por organización.
- Ordena el array por score_global descendente.

---

FORMATO FINAL — responde ÚNICAMENTE con este JSON válido, sin texto adicional,
sin bloques markdown, sin explicaciones antes o después del JSON:

{{
  "perfil": {{
    "facultad_o_programa": "",
    "competencias_profesionales": [],
    "competencias_tecnicas": [],
    "competencias_especializadas": [],
    "procesos_a_ejecutar": [],
    "sectores_economicos": [],
    "infraestructura_requerida": [],
    "entornos_laborales": [],
    "resumen_perfil": "",
    "areas_clave": []
  }},
  "tipos_institucion_relevantes": [
    {{ "valor": "snake_case", "label": "Nombre legible" }}
  ],
  "modalidades_relevantes": [],
  "organizaciones": [],
  "metadata": {{
    "total_encontradas": 0,
    "ubicacion_referencia": "",
    "pais": "",
    "radio_km": 0
  }}
}}
""".strip()


def analyze_dossier(dossier_text: str, filters: dict) -> dict:
    """
    Llama a Gemini CON Google Search grounding (SDK google-genai vigente)
    y retorna el dict con perfil + tipos/modalidades dinámicos + organizaciones.
    Lanza ValueError si el JSON es inválido.

    NOTA: grounding (tools=GoogleSearch) y response_mime_type=json no son
    compatibles simultáneamente en la API de Gemini, por eso el formato
    JSON se fuerza solo mediante instrucciones explícitas en el prompt y
    un parseo robusto, no mediante response_mime_type.
    """
    prompt = _build_prompt(dossier_text, filters)

    # IMPORTANTE: gemini-2.5-flash tiene "thinking" activado por defecto, y
    # esos tokens de razonamiento interno se restan del mismo presupuesto
    # que max_output_tokens. Acotamos el thinking a un presupuesto fijo para
    # que la búsqueda con grounding siga siendo precisa, sin dejar la
    # respuesta final sin espacio (truncamiento visto en producción).
    config = types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=65536,
        thinking_config=types.ThinkingConfig(thinking_budget=8192),
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )

    response = _client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=config,
    )

    finish_reason = None
    try:
        finish_reason = response.candidates[0].finish_reason.name
    except Exception:
        pass

    usage_info = ""
    try:
        usage = response.usage_metadata
        usage_info = (
            f"thoughts_tokens={getattr(usage, 'thoughts_token_count', '?')} "
            f"output_tokens={getattr(usage, 'candidates_token_count', '?')} "
            f"total_tokens={getattr(usage, 'total_token_count', '?')}"
        )
    except Exception:
        pass

    raw   = response.text or ""
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
                f"finish_reason={finish_reason} | {usage_info}\n"
                f"Primeros 300 caracteres: {raw[:300]}\n"
                f"Ultimos 300 caracteres: {raw[-300:]}"
            )

    return data
