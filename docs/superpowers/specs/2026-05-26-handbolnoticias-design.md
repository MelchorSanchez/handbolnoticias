# HandbolNoticias — Diseño del Agregador

**Fecha:** 2026-05-26
**Estado:** Aprobado

## Resumen

Agregador de noticias de balonmano alojado en GitHub Pages. Un script Python ejecutado diariamente via GitHub Actions fetcha RSS feeds, realiza scraping de webs sin feed, y acepta links manuales del usuario. Las noticias se almacenan en SQLite, se traducen al español automáticamente, y se renderizan como HTML estático con Jinja2.

---

## Arquitectura

**Stack:**
- Python 3.12 (fetching, scraping, traducción, renderizado)
- SQLite (almacenamiento de artículos e historial)
- Jinja2 (templates HTML)
- Tailwind CSS via CDN (estilos, sin build step)
- GitHub Actions (automatización diaria)
- GitHub Pages (hosting estático desde `docs/`)

**Flujo diario:**
```
GitHub Actions (cron: medianoche)
  → fetcher.py   (RSS + scraping + manual_links.yaml)
  → translator.py (traduce títulos/resúmenes no ES/EN)
  → renderer.py  (genera HTML en docs/)
  → git commit + push automático
```

---

## Estructura de ficheros

```
handbolnoticias/
├── config/
│   ├── sources.yaml        # Definición de fuentes RSS y scraping
│   └── manual_links.yaml   # Links manuales añadidos por el usuario
├── scripts/
│   ├── fetcher.py          # Fetcha RSS y scraping, escribe en SQLite
│   ├── translator.py       # Traduce al español usando deep-translator
│   ├── renderer.py         # Genera HTML desde templates Jinja2
│   └── run_all.py          # Orquesta el pipeline completo
├── templates/
│   ├── base.html           # Layout base (navbar, footer, Tailwind CDN)
│   ├── index.html          # Portada con últimas noticias de cada sección
│   └── section.html        # Página de sección/subsección
├── data/
│   └── articles.db         # SQLite: artículos, historial y caché de traducciones
├── docs/                   # Output estático → GitHub Pages
│   └── (generado automáticamente, no editar a mano)
├── requirements.txt
└── .github/
    └── workflows/
        └── update.yml      # GitHub Actions: daily cron
```

---

## Modelo de datos (SQLite)

### Tabla `articles`
```sql
CREATE TABLE articles (
    id          TEXT PRIMARY KEY,   -- sha256(url)[:16] para deduplicar
    url         TEXT UNIQUE NOT NULL,
    title       TEXT NOT NULL,      -- título traducido al español
    title_orig  TEXT,               -- título en idioma original
    summary     TEXT,               -- resumen traducido (primer párrafo)
    image_url   TEXT,               -- og:image o enclosure RSS
    source_name TEXT,               -- ej: "rfebm.es"
    section     TEXT NOT NULL,      -- ej: "spain/asobal", "germany/bundesliga"
    published   TEXT,               -- fecha ISO 8601
    fetched_at  TEXT NOT NULL,      -- timestamp de ingesta
    is_manual   INTEGER DEFAULT 0   -- 1 si fue añadido manualmente
);
```

### Tabla `translations`
```sql
CREATE TABLE translations (
    text_hash   TEXT PRIMARY KEY,   -- sha256(original_text)
    original    TEXT NOT NULL,
    translated  TEXT NOT NULL,
    lang_from   TEXT                -- idioma detectado (ej: "fr", "de")
);
```

**Deduplicación:** `id = sha256(url)[:16]`. Si el mismo artículo aparece en varios feeds, se ignora el duplicado.
**Histórico:** los artículos nunca se borran. La web muestra los últimos 30 días por sección.

---

## Fuentes y secciones

### España — Masculino
| Sección | slug | División |
|---------|------|----------|
| ASOBAL | `spain/asobal` | 1ª div. masculina |
| División Honor Plata | `spain/dhp` | 2ª div. masculina |
| Primera Nacional | `spain/primera-nacional-masc` | 3ª div. masculina |

### España — Femenino
| Sección | slug | División |
|---------|------|----------|
| Liga Guerreras Iberdrola | `spain/guerreras` | 1ª div. femenina |
| División Honor Oro | `spain/dho-fem` | 2ª div. femenina |
| División Honor Plata | `spain/dhp-fem` | 3ª div. femenina |

### España — Territorial
| Sección | slug |
|---------|------|
| Cataluña | `spain/catalonia` |
| Navarra | `spain/navarra` |
| País Vasco | `spain/euskadi` |

### Europa — Competiciones EHF
| Sección | slug |
|---------|------|
| Champions League EHF | `europe/champions` |
| EHF European League | `europe/european-league` |
| Otras EHF | `europe/other` |

### Internacional
| País | slug | Divisiones |
|------|------|-----------|
| Francia | `france` | Starligue (1ª), Proligue (2ª) |
| Alemania | `germany` | Bundesliga (1ª), 2. Bundesliga (2ª) |
| Dinamarca | `denmark` | 1ª |
| Suecia | `sweden` | 1ª |
| Noruega | `norway` | 1ª |
| Portugal | `portugal` | 1ª |
| Austria | `austria` | 1ª |
| Suiza | `switzerland` | 1ª |
| Islandia | `iceland` | 1ª |
| Islas Feroe | `faroe-islands` | 1ª |
| Hungría | `hungary` | 1ª |
| Polonia | `poland` | 1ª |
| Croacia | `croatia` | 1ª |
| Serbia | `serbia` | 1ª |
| Eslovaquia | `slovakia` | 1ª |
| Rumania | `romania` | 1ª |
| Argentina | `argentina` | 1ª |
| Brasil | `brazil` | 1ª |
| Japón | `japan` | 1ª |

---

## Fuentes conocidas

### Medios especializados en balonmano
| Dominio | Tipo | Secciones |
|---------|------|-----------|
| ligaasobal.es | RSS/scrape | spain/asobal |
| mibalonmano.es | RSS/scrape | spain/* |
| balonmanocentral.com | RSS/scrape | spain/*, europe/* |
| balonmano.info | RSS/scrape | spain/*, internacional |
| balonmano100x100.es | RSS/scrape | spain/* |
| cathandbol.cat | RSS/scrape | spain/catalonia |

### Diarios deportivos nacionales (sección balonmano)
| Dominio | Tipo | Secciones |
|---------|------|-----------|
| marca.com/balonmano | scrape | spain/*, europe/* |
| as.com/balonmano | scrape | spain/*, europe/* |
| mundodeportivo.com/balonmano | scrape | spain/*, europe/* |

### Diarios locales y autonómicos
Se añadirán fuentes locales durante la implementación, según cobertura territorial (Cataluña, Navarra, País Vasco y otras comunidades). Configurables via `sources.yaml`.

### Instagram *(Fase 2 — a configurar más adelante)*
Cuentas de interés identificadas: `upskill_handball`, `rthandball`, `balonmano_primera_nacional` y otras.
Integración pendiente de decidir el método de acceso (Instaloader, API oficial Meta, u otro).
La arquitectura del fetcher está preparada para añadir un tipo de fuente `instagram` en `sources.yaml` sin cambiar el resto del pipeline.

---

## Configuración de fuentes (`sources.yaml`)

Cada fuente tiene un tipo (`rss` o `scrape`) y un slug de sección:

```yaml
sources:
  - name: RFEBM
    section: spain/asobal
    type: rss
    url: https://www.rfebm.com/feed/
    max_items: 50

  - name: Federació Catalana
    section: spain/catalonia
    type: scrape
    url: https://www.handbol.cat/noticies
    selectors:
      articles: "article.news-item"
      title: "h2.title"
      link: "a[href]"
      image: "img[src]"
    max_items: 30
```

### Links manuales (`manual_links.yaml`)

```yaml
manual_links:
  - url: https://ejemplo.com/noticia-especial
    title: "Título de la noticia"       # opcional, si no se auto-extrae
    section: spain/asobal
    date: "2026-05-26"
```

---

## Fetching y scraping

**Librerías:**
- `feedparser` — parseo de RSS/Atom
- `httpx` — cliente HTTP async con timeout
- `beautifulsoup4` + `lxml` — scraping HTML
- `langdetect` — detección de idioma
- `deep-translator` — traducción (Google Translate, gratuito)

**Comportamiento:**
- Timeout 10s por fuente; si falla, se loguea y continúa con la siguiente
- User-Agent realista para evitar bloqueos básicos
- Máximo 50 artículos nuevos por fuente por ejecución
- Imagen: se extrae de `og:image`, enclosure RSS, o primer `<img>` del artículo

---

## Traducción

- Se detecta el idioma del título con `langdetect`
- Si el idioma **no es** `es` ni `en`, se traduce al español con `deep-translator`
- El resultado se cachea en la tabla `translations` (hash del texto original como clave)
- Se traduce: título completo + primeros 300 caracteres del resumen

---

## Diseño visual

**Framework:** Tailwind CSS via CDN (sin build step, compatible con GitHub Pages).

**Esquema de colores:**
- Azul handball `#003DA5` — color principal, navbar, acentos
- Naranja `#FF6B00` — destacados, etiquetas "Nuevo"
- Rojo `#CC0000` — sección España
- Verde `#2E7D32` — sección Europa
- Negro `#1A1A1A` — texto principal
- Blanco `#FFFFFF` — fondos

**Portada (`index.html`):**
- Navbar con dropdowns: España / Europa / Internacional
- Bloques por sección principal, cada uno con las 5 noticias más recientes
- Botón "Ver todo →" por bloque
- Footer: "Actualizado: 26/05/2026 a las 02:00" + enlace al repo GitHub

**Tarjeta de noticia:**
```
┌──────────────────────────────────────────┐
│ [img 120x80]  Titular de la noticia      │
│               en máximo dos líneas       │
│               rfebm.es · hace 3h         │
└──────────────────────────────────────────┘
```
- Click abre la noticia original en nueva pestaña
- Imagen placeholder si no hay imagen disponible
- Responsive: 1 columna en móvil, 2 en tablet, 3 en desktop

**Página de sección (`section.html`):**
- Lista completa de noticias de esa sección
- Últimos 30 días por defecto
- Breadcrumb: Inicio > España > ASOBAL

---

## GitHub Actions (`update.yml`)

```yaml
name: Actualizar noticias
on:
  schedule:
    - cron: '0 1 * * *'   # 01:00 UTC = 02:00 ES (hora de verano)
  workflow_dispatch:        # permite ejecución manual
jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python scripts/run_all.py
      - name: Commit y push
        run: |
          git config user.name "HandbolNoticias Bot"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add docs/ data/articles.db
          git diff --staged --quiet || git commit -m "Actualización diaria $(date +%Y-%m-%d)"
          git push
```

---

## Manejo de errores

- Cada fuente falla de forma independiente (try/except por fuente)
- Errores se loguean en `data/errors.log` (no se sube a GitHub Pages)
- Si el pipeline completo falla, el sitio mantiene el HTML de la última ejecución correcta
- Artículos sin imagen muestran placeholder SVG con el logo de balonmano

---

## Dependencias (`requirements.txt`)

```
feedparser==6.0.11
httpx==0.27.0
beautifulsoup4==4.12.3
lxml==5.2.1
langdetect==1.0.9
deep-translator==1.11.4
Jinja2==3.1.4
```
