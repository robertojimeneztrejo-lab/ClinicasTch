# 🏥 Clinical Finder — Buscador de Campos Clínicos

Webapp de geolocalización de instituciones para prácticas clínicas,
construida con Streamlit + Gemini 2.5 Flash + Google Places API + Supabase.

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Frontend / App | Streamlit |
| IA principal | Google Gemini 2.5 Flash |
| Datos de lugar | Google Places API |
| Persistencia | Supabase (PostgreSQL) |
| Mapa | Folium + streamlit-folium |
| Deploy | Streamlit Cloud |

---

## Estructura del proyecto

```
clinical_finder/
├── app.py                        # App principal
├── requirements.txt
├── .gitignore
├── .streamlit/
│   └── secrets.toml              # API keys (NO subir a Git)
├── components/
│   ├── ficha.py                  # Componente de ficha de resultado
│   └── mapa.py                   # Mapa Folium
└── utils/
    ├── gemini_client.py          # Prompt + llamada a Gemini
    ├── places_client.py          # Google Places API
    └── supabase_client.py        # Persistencia + historial
```

---

## Instalación local

```bash
# 1. Clonar repositorio
git clone https://github.com/TU_USUARIO/clinical-finder.git
cd clinical-finder

# 2. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
.venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar secrets
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Editar .streamlit/secrets.toml con tus API keys

# 5. Ejecutar
streamlit run app.py
```

---

## Configuración de secrets

Edita `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY        = "AIza..."
GOOGLE_PLACES_API_KEY = "AIza..."   # Pendiente — ver instrucciones abajo

[supabase]
url = "https://xxxx.supabase.co"
key = "eyJ..."
```

---

## Esquema Supabase

Ejecuta en **Supabase → SQL Editor**:

```sql
CREATE TABLE searches (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz DEFAULT now(),
    regions     text[],
    location    text,
    radius_km   int,
    modalities  text[],
    inst_types  text[],
    min_specs   int,
    max_results int,
    perfil_json jsonb
);

CREATE TABLE results (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    search_id       uuid REFERENCES searches(id) ON DELETE CASCADE,
    created_at      timestamptz DEFAULT now(),
    nombre          text,
    tipo_institucion text,
    pais            text,
    ciudad          text,
    direccion       text,
    lat             float,
    lng             float,
    telefono        text,
    email           text,
    sitio_web       text,
    jefe_ensenanza  text,
    cargo_jefe      text,
    jefe_verificado boolean DEFAULT false,
    especialidades  jsonb,
    modalidades     text[],
    score_global    float,
    rating_google   float,
    num_resenas     int,
    maps_url        text,
    foto_url        text,
    horario_24h     boolean,
    abierto_ahora   boolean,
    menciones_estud jsonb,
    justificacion   text,
    raw_json        jsonb
);
```

---

## Obtener Google Places API key

1. Ve a [console.cloud.google.com](https://console.cloud.google.com)
2. Crea un proyecto o selecciona uno existente
3. Activa **Places API** en "APIs y servicios"
4. Crea una API key en "Credenciales"
5. Pégala en `secrets.toml` bajo `GOOGLE_PLACES_API_KEY`

> La app funciona sin esta key (modo degradado: sin foto, rating ni reseñas).

---

## Deploy en Streamlit Cloud

1. Sube el repositorio a GitHub (sin `secrets.toml`)
2. Ve a [share.streamlit.io](https://share.streamlit.io)
3. Conecta el repo → selecciona `app.py`
4. En **Secrets**, pega el contenido de tu `secrets.toml`
5. Deploy ✅

---

## Flujo de la app

```
PDF dossier → Gemini 2.5 Flash → JSON estructurado
                                      ↓
                            Google Places API (enriquecimiento)
                                      ↓
                            Supabase (persistencia)
                                      ↓
                    Mapa Folium + Fichas de resultado
```
