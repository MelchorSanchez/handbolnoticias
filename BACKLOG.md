# Backlog

Ideas pendientes, por orden de prioridad.

## 1. Medir el clasificador con precisión y recall

Hoy cada cambio de regla se prueba pasándola por toda la DB y revisando a ojo
los titulares que cambian. Los artículos corregidos a mano (`is_manual=1`, unos
740 en oct-2026) sirven como conjunto de referencia gratuito.

- Script que pase `classify()` por esos artículos y compare con su sección y
  `extra_sections` guardadas.
- Precisión y recall por sección (ej. `fichajes`, `spain/asobal`) y lista de
  fallos concretos (falsos positivos / negativos).
- Ejecutarlo antes y después de cada cambio en `classifier.py`
  o `classifier_rules.yaml` para ver si mejora o empeora algo.

Idea tomada de la evaluación de cribado como clasificador binario
(Whitehouse et al., *J. Chem. Inf. Model.* 2024, doi:10.1021/acs.jcim.4c00679).

## 2. Informe de salud por fuente

El 28-oct-2026 la Action se colgó 70 min por un feed sin timeout, y al
arreglarlo aparecieron 8 feeds que llevaban tiempo devolviendo 0 artículos sin
que nadie lo notara (bloqueo de WAF al user-agent de feedparser).

- Registrar por fuente: artículos descargados, artículos que pasan el filtro,
  duración y error, si lo hay.
- Resumen al final de cada ejecución en el log de la Action.
- Aviso si una fuente lleva más de N días sin aportar artículos o da error
  repetidamente.

## 3. Descargar las fuentes en paralelo (baja prioridad)

Descargar los ~110 feeds en paralelo (ThreadPool) tarda segundos en vez de
minutos. La Action ya tarda unos 5 min, así que la ganancia es pequeña.

## Descartado

- Cascada de dos fases para detectar duplicados de títulos: con unos 8.000
  artículos la comparación actual (48 h, solape de palabras) es instantánea.
