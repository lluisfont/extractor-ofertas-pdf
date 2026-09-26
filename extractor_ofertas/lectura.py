"""Capas de lectura: PyMuPDF (principal), pdfplumber (triangulación) y OCR (respaldo)."""
from __future__ import annotations

import logging
import re

import pymupdf

from .config import Config
from .modelos import Palabra

log = logging.getLogger(__name__)

# Caracteres que los PDFs suelen codificar de forma rara
_EQUIVALENCIAS = str.maketrans({"­": "-", "‐": "-", "‑": "-", "‒": "-", "–": "-",
                                "—": "-", "−": "-", " ": " ", " ": " ", " ": " ",
                                "ﬁ": "fi", "ﬂ": "fl", "₠": "€"})


def normalizar(texto: str) -> str:
    return texto.translate(_EQUIVALENCIAS)


def palabras_pymupdf(pagina: pymupdf.Page) -> list[Palabra]:
    """Palabras con caja y tamaño de letra reales, construidas carácter a carácter."""
    palabras: list[Palabra] = []
    datos = pagina.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_LIGATURES | pymupdf.TEXT_MEDIABOX_CLIP)
    for bloque in datos["blocks"]:
        if bloque.get("type") != 0:
            continue
        for linea in bloque["lines"]:
            dx, dy = linea.get("dir", (1, 0))
            if abs(dy) > 0.2:  # texto girado: se ignora en la agrupación
                continue
            for span in linea["spans"]:
                negrita = bool(span["flags"] & 16) or "bold" in span["font"].lower()
                actual: list = []
                for ch in span["chars"] + [{"c": " ", "bbox": None}]:
                    ch = dict(ch, c=normalizar(ch["c"]))
                    if ch["c"].isspace():
                        if actual:
                            texto = "".join(c["c"] for c in actual)
                            palabras.append(Palabra(
                                texto=texto,
                                x0=min(c["bbox"][0] for c in actual), y0=min(c["bbox"][1] for c in actual),
                                x1=max(c["bbox"][2] for c in actual), y1=max(c["bbox"][3] for c in actual),
                                tamano=round(span["size"], 2), negrita=negrita, motor="pymupdf"))
                            actual = []
                    else:
                        actual.append(ch)
    return palabras


def palabras_pdfplumber(pagina_plumber) -> list[Palabra]:
    try:
        crudas = pagina_plumber.extract_words(extra_attrs=["size", "fontname"],
                                              keep_blank_chars=False, use_text_flow=False)
    except Exception as e:  # pdfplumber puede fallar con PDFs raros
        log.warning("pdfplumber falló en página: %s", e)
        return []
    return [Palabra(texto=normalizar(w["text"]), x0=w["x0"], y0=w["top"], x1=w["x1"], y1=w["bottom"],
                    tamano=round(w.get("size", w["bottom"] - w["top"]), 2),
                    negrita="bold" in str(w.get("fontname", "")).lower(), motor="pdfplumber")
            for w in crudas if w["text"].strip()]


def motor_ocr(cfg: Config) -> str | None:
    """OCR disponible: «rapidocr» (preferido: mejor con números de folleto) o «tesseract»."""
    if not cfg.ocr_activo:
        return None
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return "rapidocr"
    except ImportError:
        pass
    ruta = cfg.ruta_tesseract()
    if ruta:
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = ruta
            pytesseract.get_tesseract_version()
            return "tesseract"
        except Exception:
            pass
    return None


def ocr_disponible(cfg: Config) -> bool:
    return motor_ocr(cfg) is not None


def palabras_ocr(pagina: pymupdf.Page, cfg: Config) -> list[Palabra]:
    if motor_ocr(cfg) == "rapidocr":
        return _palabras_rapidocr(pagina)
    return _palabras_tesseract(pagina, cfg)


_RAPIDOCR = None
_EURO_OCR = re.compile(r"(\d)\s*[eE€](?![a-zA-ZáéíóúñÁÉÍÓÚÑ])")  # el OCR suele leer «€» como «e»
# El OCR confunde el «€» pequeño con «6», «e», «E», «C» o «t» pegados a los céntimos («2,566Kilo» = 2,56 €/kg,
# «3,03t Litro»), o lo omite delante de «Kilo»/«Litro» («(3,28 Kilo)»), de «100 ml» («(2,00100ml)»,
# «4,486100ml») o detrás de «unidad:» («Llevando 1 unidad: 1,89»).
_EURO_POR_100 = re.compile(r"(\d+[,.]\d{2})[6eECt€]?(?=\s*/?\s*100\s*(?:ml|g)\b)", re.IGNORECASE)
_EURO_TRAS_CENTIMOS = re.compile(r"(\d+[,.]\d{2})[6eECt](?=[\s)\]]|$|[A-Za-z])")
_EURO_ANTES_UNIDAD = re.compile(r"(\d+[,.]\d{2})(?=\s*(?:kilo|litro)s?\b)", re.IGNORECASE)
_EURO_TRAS_UNIDAD = re.compile(r"(unidad(?:es)?\s*:?\s*)(\d+[,.]\d{2})(?!\s*€)", re.IGNORECASE)


def _euro_ocr(texto: str) -> str:
    texto = _EURO_POR_100.sub(lambda m: m.group(1) + "€/", texto)
    texto = _EURO_TRAS_CENTIMOS.sub(lambda m: m.group(1) + "€", texto)
    texto = _EURO_ANTES_UNIDAD.sub(lambda m: m.group(1) + "€", texto)
    texto = _EURO_TRAS_UNIDAD.sub(lambda m: m.group(1) + m.group(2) + "€", texto)
    return _EURO_OCR.sub(lambda m: m.group(1) + "€", texto)


_PRECIO_COMPLETO = re.compile(r"\d+[,.]\d{2}")


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def _palabras_rapidocr(pagina: pymupdf.Page) -> list[Palabra]:
    """OCR a varias escalas: cada escala acierta cosas distintas (p. ej. el «1» delgado de «1,95»).
    Las lecturas de la misma zona se fusionan quedándose con la más completa."""
    global _RAPIDOCR
    if _RAPIDOCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _RAPIDOCR = RapidOCR()
    lecturas = []  # (caja, texto, confianza)
    for escala in (1.25, 2.0, 2.75):
        pix = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False)
        res, _ = _RAPIDOCR(pix.tobytes("png"))
        for caja, texto, conf in res or []:
            xs, ys = [p[0] / escala for p in caja], [p[1] / escala for p in caja]
            texto = _euro_ocr(normalizar(texto.strip()))
            if texto:
                lecturas.append(((min(xs), min(ys), max(xs), max(ys)), texto, float(conf)))

    def calidad(l):
        _, t, c = l
        return (bool(_PRECIO_COMPLETO.search(t)), len(t), c)

    elegidas = []
    for l in sorted(lecturas, key=calidad, reverse=True):
        if any(_iou(l[0], e[0]) > 0.3 for e in elegidas):
            continue
        elegidas.append(l)
    return [Palabra(texto=t, x0=c[0], y0=c[1], x1=c[2], y1=c[3], tamano=round((c[3] - c[1]) * 0.85, 2), motor="ocr")
            for c, t, conf in elegidas if conf >= 0.5]


def _palabras_tesseract(pagina: pymupdf.Page, cfg: Config) -> list[Palabra]:
    import pytesseract
    from PIL import Image

    pytesseract.pytesseract.tesseract_cmd = cfg.ruta_tesseract()
    escala = cfg.ocr_dpi / 72
    pix = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    try:
        datos = pytesseract.image_to_data(img, lang=cfg.ocr_idioma, config="--psm 11",
                                          output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractError:
        # Idioma no instalado: reintento con inglés
        datos = pytesseract.image_to_data(img, config="--psm 11", output_type=pytesseract.Output.DICT)
    palabras = []
    for i, texto in enumerate(datos["text"]):
        texto = (texto or "").strip()
        conf = float(datos["conf"][i])
        if not texto or conf < cfg.ocr_confianza_minima:
            continue
        x, y, w, h = (datos[k][i] / escala for k in ("left", "top", "width", "height"))
        palabras.append(Palabra(texto=_euro_ocr(normalizar(texto)), x0=x, y0=y, x1=x + w, y1=y + h,
                                tamano=round(h * 1.1, 2), motor="ocr"))
    return palabras


def cobertura_imagenes(pagina: pymupdf.Page) -> float:
    """Fracción aproximada de la página cubierta por imágenes."""
    area_pag = pagina.rect.width * pagina.rect.height or 1
    area = 0.0
    for info in pagina.get_image_info():
        r = pymupdf.Rect(info["bbox"]) & pagina.rect
        area += r.width * r.height
    return min(area / area_pag, 1.0)


def trazos_tachado(pagina: pymupdf.Page) -> list[tuple[float, float, float, float]]:
    """Segmentos finos (líneas o rectángulos muy estrechos) que pueden tachar un precio."""
    segmentos = []
    try:
        dibujos = pagina.get_drawings()
    except Exception:
        return segmentos
    for d in dibujos:
        solo_trazo = d.get("fill") is None and "s" in (d.get("type") or "")
        for item in d.get("items", []):
            if item[0] == "l" and solo_trazo:
                # Una línea trazada; los bordes de formas rellenas (recuadros de precio) no tachan
                p1, p2 = item[1], item[2]
                segmentos.append((p1.x, p1.y, p2.x, p2.y))
            elif item[0] == "re":
                r = item[1]
                if r.height <= 2.5 and r.width > 4 and len(d.get("items", [])) == 1:
                    segmentos.append((r.x0, r.y0 + r.height / 2, r.x1, r.y0 + r.height / 2))
    return segmentos


def contenedores(pagina: pymupdf.Page) -> list[tuple[float, float, float, float]]:
    """Recuadros dibujados (celdas del folleto) útiles para separar ofertas vecinas."""
    area_pag = pagina.rect.width * pagina.rect.height or 1
    cajas = []
    try:
        dibujos = pagina.get_drawings()
    except Exception:
        return cajas
    for d in dibujos:
        r = d.get("rect")
        if r is None:
            continue
        fraccion = (r.width * r.height) / area_pag
        if 0.005 <= fraccion <= 0.6 and r.width > 30 and r.height > 30:
            cajas.append((r.x0, r.y0, r.x1, r.y1))
    return cajas
