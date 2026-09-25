# Extractor de ofertas de folletos PDF

Copia un folleto PDF en `entrada/` y en unos segundos tendrás en `salida/` un Excel
con todas las ofertas extraídas y un informe de verificación de integridad.

## Instalación (Windows)

```bash
pip install -r requirements.txt
```

**OCR (opcional, para folletos escaneados o con precios en imagen):** instala
[Tesseract para Windows](https://github.com/UB-Mannheim/tesseract/wiki) marcando el
idioma *Spanish*. Se detecta solo en `C:\Program Files\Tesseract-OCR`. Sin Tesseract,
las páginas que son imagen se marcan como **ERROR** en el Excel (no se pierden en silencio).

## Uso

- **Modo automático:** doble clic en `iniciar_vigilante.bat` (o `python -m extractor_ofertas`).
  Cada PDF que aparezca en `entrada/` se procesa cuando termina de copiarse; el Excel va a
  `salida/` y el PDF se mueve a `procesados/` (o a `errores/` con un `.error.txt` si falla).
  Los PDFs que ya estaban en `entrada/` al arrancar también se procesan.
- **Modo manual:** `python -m extractor_ofertas procesar folleto.pdf [--salida carpeta]`

Registro de actividad en `logs/extractor.log`.

## Cómo funciona

1. **Lectura híbrida**
   - *PyMuPDF* carácter a carácter: texto, coordenadas y tamaño de letra.
   - *pdfplumber* en paralelo (**triangulación**): si ve un precio que PyMuPDF no vio, se añade.
   - *OCR Tesseract* de respaldo cuando la página no tiene capa de texto.
2. **Líneas visuales por coordenadas:** solo se unen palabras que se solapan en vertical y
   están cerca, así las columnas y cuadrículas no se mezclan. Reconstruye precios con
   céntimos en superíndice (`1` `99` `€` → `1,99 €`).
3. **Clasificación de precios:** principal, anterior (tachado con una línea dibujada o
   precedido de "antes/PVP"), unitario (`€/kg`, `€/l`...), 2ª unidad, o secundario por tamaño.
4. **Agrupación espacial:** cada precio principal es una oferta; los textos y precios
   secundarios se asignan al más cercano, respetando los recuadros dibujados de las celdas.
5. **Interpretación:** producto, marca, formato, promoción (2x1, 3x2, 2ª unidad al 50 %,
   -20 %...), condiciones (tarjeta, online, máx. uds...), descuento calculado, sección y vigencia.

## Verificación (lo que evita perder ofertas)

| Control | Qué hace |
|---|---|
| Conteo de control con `€` | Compara los precios con `€` del texto bruto de cada página con los reconocidos, y lista los importes que faltan. |
| Triangulación | Ejecuta PyMuPDF y pdfplumber y une lo que encuentra cada uno. |
| Precios huérfanos | Todo precio detectado debe acabar en una oferta; si no, se avisa. |
| Calidad de bloque | Precios sin descripción, descripciones sospechosamente largas (dos productos mezclados), precio anterior menor que el de oferta. |
| Páginas de imagen | Página sin texto o con mucha imagen y sin precios → aviso o error. |

## El Excel generado

- **Resumen:** totales, vigencia y **estado de verificación** (verde/amarillo/rojo).
- **Ofertas:** una fila por oferta; las filas con alertas se resaltan en amarillo.
- **Auditoria_paginas:** conteos por página y por motor.
- **Incidencias:** qué revisar a mano y por qué.
- **Texto_bruto:** cada línea leída, con posición y a qué oferta se asignó (trazabilidad).

## Ajustes

Copia `config.ejemplo.json` a `config.json` y cambia lo que necesites (umbrales de
agrupación, OCR, carpetas...). Cada cadena de supermercado maqueta distinto: si en un
folleto real se mezclan productos vecinos, ajusta `radio_asociacion_*` y
`penalizacion_texto_debajo`.

## Tests

```bash
python -m pytest tests -q
```

Genera un folleto sintético (cuadrícula, céntimos en superíndice, precios tachados, €/kg,
promociones y una página de imagen) y comprueba cada campo extraído.
