"""Capas de lectura: PyMuPDF (principal), pdfplumber (triangulación) y OCR (respaldo)."""
from __future__ import annotations

import logging

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


def ocr_disponible(cfg: Config) -> bool:
    if not cfg.ocr_activo:
        return False
    ruta = cfg.ruta_tesseract()
    if not ruta:
        return False
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = ruta
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def palabras_ocr(pagina: pymupdf.Page, cfg: Config) -> list[Palabra]:
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
        palabras.append(Palabra(texto=normalizar(texto), x0=x, y0=y, x1=x + w, y1=y + h,
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
