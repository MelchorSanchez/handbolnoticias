# Ejecutar el pipeline a mano

El sitio se actualiza solo: la Action `Actualizar noticias`
(`.github/workflows/update.yml`) corre a las 07:10, 14:10 y 21:10 (GMT+2),
hace commit de lo generado y Cloudflare Pages despliega desde `main`.

Esto es para cuando quieras ejecutarlo tú, normalmente después de cambiar el
clasificador, las fuentes o las plantillas.

## 1. Antes de nada: `git pull`

```bash
cd ~/science/handbolnoticias
git pull
```

**Imprescindible.** `data/articles.db` y `docs/` los escribe también la Action,
y la base de datos es un binario: si editas sobre una copia vieja, el siguiente
pull choca y hay que resolverlo a mano. Si ya tienes cambios locales sin
commitear en el DB, no hagas `stash` con él — commitea o descarta antes.

## 2. Ejecutar

La clave de DeepL vive en `.env` (no está en git). Hay que exportarla antes:

```bash
set -a && . ./.env && set +a
python3 scripts/run_all.py
```

Sin `DEEPL_API_KEY` el pipeline corre igual, pero no traduce los titulares que
no estén en español (quedan pendientes y se traducen en la siguiente ejecución
que sí tenga la clave).

Tarda unos 3-5 minutos: la mayor parte es descargar las ~100 fuentes. Al final
imprime el **informe de salud de las fuentes** (fuentes con error, fuentes que
responden pero sin entradas, y las que llevan 30 días sin aportar nada). Vale la
pena leerlo: es lo que detecta un feed roto el mismo día.

Lo que hace, en orden: descarga → filtra → clasifica → traduce → inserta en
`data/articles.db` → informe de salud → corrige fechas → renderiza `docs/` →
podcasts → resultados y clasificaciones.

Dos avisos que son normales en local y no hay que arreglar:

- `pagefind binary not found at /tmp/pagefind, skipping search index` — el
  índice de búsqueda solo se genera en la Action.
- `No es viernes/sábado/domingo: no se piden resultados nuevos` — los
  resultados solo se descargan en fin de semana.

## 3. Subir

```bash
git add -A docs data/articles.db sitemap.xml
git commit -m "Actualización diaria $(date -u +%Y-%m-%d)"
git push
```

Si además has tocado código o configuración, inclúyelo en el mismo commit y
explica el porqué en el mensaje.

## Partes sueltas

Cada paso se puede ejecutar por su cuenta sin volver a descargar nada:

```bash
python3 scripts/renderer.py        # solo re-renderizar docs/ desde el DB
python3 scripts/podcasts.py        # solo la página de podcasts
python3 scripts/results.py         # resultados y clasificaciones
python3 scripts/source_health.py   # informe de salud desde el estado guardado
python3 scripts/audit_articles.py  # buscar artículos sospechosos/basura
```

## Antes de tocar el clasificador

No hay tests unitarios del clasificador: se mide. Las dos medidas, siempre
antes y después del cambio:

```bash
# Precisión/recall sobre los artículos corregidos a mano (is_manual = 1)
python3 scripts/eval_classifier.py --save /ruta/antes.json
# ...haces el cambio...
python3 scripts/eval_classifier.py --compare /ruta/antes.json
```

El criterio para aceptar un cambio: **0 empeoramientos** sobre esos artículos
manuales y los cambios en el resto de la base deben ser todos revisables uno a
uno (una regla que mueve decenas de artículos casi siempre está mal). Si una
regla general no pasa el corte, el arreglo correcto es puntual: `UPDATE` de la
fila con `is_manual = 1`, que impide que el pipeline lo revierta.

`python3 -m pytest -q` cubre fetcher, db, renderer, traductor y salud de
fuentes; hay que dejarlo en verde.
