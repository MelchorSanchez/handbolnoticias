# HandbolNoticias

**Agregador de noticias de balonmano en español.**

🌐 [handbolnoticias.pages.dev](https://handbolnoticias.pages.dev)

---

## Qué es esto

HandbolNoticias recopila y clasifica automáticamente noticias de balonmano publicadas por otros medios: webs de clubes, federaciones, medios especializados y cuentas de redes sociales. No producimos contenido propio — enlazamos siempre a la fuente original.

Cubrimos:

- 🇪🇸 **España** — ASOBAL, Liga Guerreras Iberdrola, División de Honor, selecciones nacionales y balonmano base
- 🇪🇺 **Europa EHF** — Champions League, European League, European Cup y EHF EURO
- 🌍 **IHF** — Mundiales masculino y femenino
- 🇩🇪 **Alemania** — Daikin HBL, Alsco HBF y 2. Bundesliga
- 🇫🇷 **Francia** — Starligue, ProLigue, D1F y D2F
- 🌐 **Internacional** — Dinamarca, Noruega, Suecia, Portugal, Croacia, Polonia y más

## Cómo funciona

Un pipeline Python se ejecuta periódicamente y realiza estos pasos:

```
Fetch → Classify → Translate → Render
```

1. **Fetch** — obtiene artículos de ~72 fuentes (RSS, scraping web, Instagram)
2. **Classify** — asigna cada artículo a una o más secciones usando reglas de keywords, nombres de equipos y señales de género gramatical
3. **Translate** — traduce los títulos al español cuando el artículo está en otro idioma
4. **Render** — genera el HTML estático con Jinja2 y lo publica en `docs/`

El sitio es completamente estático: no hay servidor, no hay base de datos en producción. Se despliega automáticamente en Cloudflare Pages desde la rama `main`.

## Estructura

```
config/
  sources.yaml          # Fuentes de noticias (~72 fuentes)
  teams.yaml            # Equipos por sección (para clasificación por nombre)
  classifier_rules.yaml # Reglas de keywords por sección
scripts/
  fetcher.py            # Obtención de artículos
  classifier.py         # Clasificación por sección
  translator.py         # Traducción de títulos
  renderer.py           # Generación del HTML estático
  run_all.py            # Orquestador del pipeline completo
  db.py                 # Capa de acceso a SQLite
templates/              # Plantillas Jinja2
docs/                   # Site estático generado (desplegado en Cloudflare Pages)
data/articles.db        # Base de datos SQLite local
```

## Requisitos

```bash
pip install -r requirements.txt
```

## Ejecutar el pipeline

```bash
python scripts/run_all.py
```

Genera el site completo en `docs/`.

## Aviso legal

HandbolNoticias es un agregador. Todo el contenido pertenece a sus autores y medios originales. Este proyecto no tiene afiliación con la RFEBM, EHF, IHF ni ninguna liga o club mencionado.
