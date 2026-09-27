# Extractor de ofertas de folletos PDF

Folleto PDF en `entrada/` → Excel con todas las ofertas en `salida/`. El modelo interpreta cada página
(imagen + texto) y el código verifica los importes contra el texto del PDF (o contra el OCR si el PDF
es solo de imágenes). Criterios de extracción: `extractor_ofertas/criterios.py` (única fuente).

## Procesar un folleto desde Claude Code

1. **Copiar** el PDF a `entrada/` con un nombre corto (`carrefour.pdf`, `eroski.pdf`...).
2. **Si es una cadena nueva, calibrar antes de extraer:**
   - `python -m extractor_ofertas.consola_ia controlar entrada/X.pdf`. Solo son aceptables las falsas
     alarmas de formatos («1,25 L»). Cualquier otro importe sin detectar o precio no reconstruible es
     un fallo del detector (`lineas.py`, `precios.py`, `lectura.py`): corregirlo y volver a controlar.
     Comprobar después que los folletos ya procesados siguen limpios (ver «Regresiones»).
   - Prueba piloto: `leer` una página complicada y cotejar la lista P# con la imagen, uno a uno.
   - Si el PDF es solo de imágenes, se usa OCR: cotejar a mano el OCR de dos páginas.
3. **Extraer en paralelo:** repartir las páginas entre subagentes (~10-13 páginas cada uno). Cada agente:
   `consola_ia criterios` (leerlos), y por página `leer` → mirar el PNG con Read → escribir el JSON →
   `guardar` → corregir hasta `VERIFICADA` / `VERIFICADA (OCR)`. Pedirles que informen de precios
   impresos que no salgan en la lista P# (fallos del detector) y de los avisos que dejen.
4. **Avisos que quedan:**
   - Precios enteros de círculo en páginas OCR (`enteros_ocr`): segunda lectura con agentes nuevos que
     solo confirman «producto → importe» contra la imagen.
   - Importes comprobados a mano: anotarlos en `salida/.sesiones/<folleto>/revisiones.json`
     (`{"página": [{"producto", "campo", "valor", "nota"}]}`); el Excel los muestra como «Comprobado a mano».
5. **Excel:** `consola_ia excel entrada/X.pdf` (si ya existe, crea uno con fecha: sustituir el anterior).

## Si se cambia el detector con páginas ya guardadas

Los identificadores P# cambian. Antes de cambiar el código, guardar el mapa de descartes
(id → importe y posición) y después reverificar todas las páginas reasignando cada descarte por importe
y posición. Las ofertas no dependen de los P#: solo los descartes.

## Regresiones

- `python -m pytest tests -q` (folleto sintético).
- `consola_ia controlar` sobre los folletos reales que haya en `entrada/` o `procesados/`
  (Carrefour, Eroski: solo deben quedar falsas alarmas de formato).

## Trampas conocidas

- **Barras invertidas en la terminal:** al pasar código Python por Bash, `\\` llega como `\`, y `\b` o `\1`
  acaban como caracteres de control dentro de las expresiones regulares. Editar las regex con la
  herramienta Edit/Write, no con heredocs; si hace falta en Bash, usar `chr(92)`.
- El `stdout` del servidor MCP (`servidor_mcp.py`) es el canal del protocolo: nada de `print`; el log va a
  `logs/mcp.log`.
- `entrada/`, `salida/`, `procesados/` y las sesiones no se suben a git.
