"""Interpretación de cada bloque de oferta: producto, marca, formato, promoción, precios..."""
from __future__ import annotations

import re

from .modelos import Linea, Oferta
from .precios import PATRON_PRECIO

PROMOCIONES = [
    ("NxM", re.compile(r"(?<![\d.,])([2-9])\s?[xX×]\s?([1-8])(?!\s?\d|\s?(?:cl|ml|l|g|kg|gr|uds?|rollos|m)\b)")),
    ("2ª unidad", re.compile(r"([2-9])\s?[ªa]\.?\s*(?:unidad|ud\.?)\s*(?:al|a)?\s*(-?\s?\d{1,3}\s?%|mitad\s+de\s+precio|gratis)",
                             re.IGNORECASE)),
    ("Descuento %", re.compile(r"(?:-\s?(\d{1,3})\s?%|(\d{1,3})\s?%\s*(?:de\s+)?(?:dto\.?|descuento|ahorro))", re.IGNORECASE)),
    ("Ahorro", re.compile(r"ahorr[ao]s?\s*:?\s*(\d+[,.]?\d*\s?€?)", re.IGNORECASE)),
    ("Regalo", re.compile(r"\b(gratis|de\s+regalo|regalo)\b", re.IGNORECASE)),
    ("Lote", re.compile(r"\b(lote|pack\s+ahorro|formato\s+ahorro)\b", re.IGNORECASE)),
]
CONDICIONES = re.compile(
    r"(con\s+(?:tu\s+|la\s+)?tarjeta[\w\s]{0,20}|club\s+\w+|socios?|app\b|solo\s+online|online|"
    r"hasta\s+fin\s+de\s+existencias|unidades\s+limitadas|m[aá]x(?:imo)?\.?\s*\d+\s*(?:uds?|unidades)|"
    r"en\s+tu\s+pr[oó]xima\s+compra|para\s+tu\s+pr[oó]xima\s+compra|acumula[\w\s]{0,20})", re.IGNORECASE)
_ENVASE = r"(?:lata|botella|brick|bote|tarro|paquete|bolsa|caja|bandeja|garrafa|malla|tarrina|sobre|barqueta)"
FORMATO = re.compile(
    rf"(?:pack\s+(?:de\s+)?\d+\s*(?:x\s*\d+(?:[.,]\d+)?\s*(?:cl|ml|l|g|gr|kg)|unidades|uds?\.?|latas|botellas)?|"
    rf"(?:{_ENVASE}\s+(?:de\s+)?)?\d+\s?x\s?\d+(?:[.,]\d+)?\s?(?:cl|ml|l|g|gr|kg)\b|"
    rf"(?:{_ENVASE}\s+(?:de\s+)?)?\d+(?:[.,]\d+)?\s?(?:kg|g|gr|grs|l|lt|litros?|ml|cl|lavados|rollos|dosis|c[aá]psulas)\b"
    rf"(?:\s+aprox\.?)?|"
    rf"\b(?:granel|al\s+corte|pieza|varios\s+modelos(?:\s+y\s+colores)?))", re.IGNORECASE)

# Etiquetas del folleto que acompañan a los precios y no forman parte del producto
ETIQUETAS = re.compile(
    r"(comprando\s+\d+\s*,?\s*(?:la|el)\s+\w+\s+sale\s+a|"
    r"(?:la|el)\s+(?:\d\s?[ªa]\s+)?(?:unidad|ud|lata|botella|pack|kg|kilo|litro|l|rollo|par|bandeja|lavado|dosis)\s+sale\s+a|"
    r"(?<!\w)\d+\s+(?:unidad(?:es)?|uds?|packs?|latas|botellas|bandejas)(?=\s*(?:\||$|\d))|"
    r"\b(?:el|la)\s+(?:kg|kilo|litro|l|unidad|par)\b(?=\s*(?:\||$|\d))|"
    r"n\s?o\s?v\s?e\s?d\s?a\s?d|novedad|aprox\.|cup[oó]n\s+de|para\s+tu\s+pr[oó]xima\s+compra|"
    r"\(\d\)|\bantes\b|\bahora\b|\bpvp\b)", re.IGNORECASE)
_NOTA_PRECIO = re.compile(r"(comprando\s+\d+\s*,?\s*(?:la|el)\s+\w+\s+sale\s+a|(?:la|el)\s+(?:\d\s?[ªa]\s+)?"
                          r"(?:unidad|ud|lata|botella|pack|rollo|par|bandeja)\s+sale\s+a)", re.IGNORECASE)
_NO_MARCA = {"XXL", "TODOS", "TODAS", "TODO", "TODA", "EN", "NOVEDAD", "IGP", "DOP", "BIO", "ECO", "LOS", "LAS", "EL",
             "LA", "DE", "Y", "O", "CON", "SIN", "PACK", "AHORRO", "FORMATO", "OFERTA", "PROMO", "NUEVO", "NUEVA",
             "XL", "XXXL", "UHT", "ESL", "ALTO", "CONTENIDO", "EXTRA", "GRATIS", "DESCUENTO", "HASTA", "PARA", "TU",
             "PRÓXIMA", "COMPRA", "CUPÓN", "LITROS", "LITRO", "KG", "ML", "CL", "OMEGA", "LED", "HD", "USB", "TV"}
_MARCA_PROPIA = re.compile(r"\bCarrefour(?:\s+(?:El\s+Mercado|BIO|Classic|Extra|Discount|Sensation|Original|Baby|Kids|"
                           r"Home|Soft|Veggie|Selección|Essential))?", re.IGNORECASE)
_RUIDO = re.compile(r"^[\s€/.,:;*+\-–()%|]*$")


def _quitar_precios(texto: str) -> str:
    def rep(m):
        return "" if (m.group("cent") or (m.group("eur") and m.group("eur").strip())) else m.group(0)
    t = PATRON_PRECIO.sub(rep, texto)
    t = re.sub(r"(?:€|eur(?:os)?)?\s*/\s*(?:kg|l|ud|kilo|litro)\b", "", t, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", t).strip()


def _en_columnas(lineas: list[Linea]) -> list[Linea]:
    """Ordena por columnas (líneas que se solapan en horizontal) y dentro de cada una de
    arriba abajo, para no intercalar la descripción con el recuadro del precio."""
    columnas: list[list[Linea]] = []
    for l in sorted(lineas, key=lambda l: (l.x0, l.y0)):
        for col in columnas:
            cx0, cx1 = min(x.x0 for x in col), max(x.x1 for x in col)
            if min(cx1, l.x1) - max(cx0, l.x0) > 0.3 * min(cx1 - cx0, l.x1 - l.x0):
                col.append(l)
                break
        else:
            columnas.append([l])
    columnas.sort(key=lambda c: min(x.x0 for x in c))
    return [l for col in columnas for l in sorted(col, key=lambda x: x.y0)]


def _marca(texto: str, lineas_desc: list[tuple[Linea, str]]) -> str:
    # 1) Secuencia de palabras en MAYÚSCULAS dentro de la descripción (ALTORREAL, SÁNCHEZ ALCARAZ...)
    tokens = re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ&'.-]+", texto)
    mejor, actual = [], []
    for tok in tokens + [""]:
        letras = [c for c in tok if c.isalpha()]
        es_mayus = len(letras) >= 2 and all(c.isupper() for c in letras) and tok.strip(".").upper() not in _NO_MARCA
        if es_mayus:
            actual.append(tok)
        else:
            if actual and not mejor:
                mejor = actual
            actual = []
    if mejor:
        return " ".join(mejor).strip(".")
    # 2) Marca propia de la cadena
    m = _MARCA_PROPIA.search(texto)
    return m.group(0) if m else ""


def interpretar(of: Oferta) -> None:
    ordenadas = _en_columnas(of.lineas)
    textos = [l.texto.strip() for l in ordenadas]
    completo = " | ".join(t for t in textos if t)
    c: dict = {}
    sello = of.precio.tipo == "sello"

    # --- precios ---
    c["precio_oferta"] = None if sello else of.precio.valor
    sec = of.secundarios
    anteriores = [p for p in sec if p.tipo == "anterior"]
    otros = [p for p in sec if p.tipo == "secundario" and not sello and p.valor > of.precio.valor]
    if anteriores or otros:
        c["precio_anterior"] = max((anteriores or otros), key=lambda p: (p.tachado, p.tamano)).valor
    unitarios = [p for p in sec if p.tipo == "unitario"]
    vigentes = [p for p in unitarios if not p.tachado]
    if vigentes:
        c["precio_unitario"] = min(p.valor for p in vigentes)
        c["unidad_precio_unitario"] = "€/" + min(vigentes, key=lambda p: p.valor).unidad
        normales = [p.valor for p in unitarios if p.tachado or p.valor > c["precio_unitario"]]
        if normales:
            c["precio_unitario_normal"] = max(normales)
    totales = [p for p in sec if p.tipo == "total"]
    if totales:
        c["precio_total_lote"] = totales[0].valor
        c["unidades_lote"] = totales[0].unidad
    cupones = [p for p in sec if p.tipo == "cupon"]
    if cupones:
        c["cupon"] = max(p.valor for p in cupones)
    segunda = [p for p in sec if p.tipo == "segunda_unidad"]
    if segunda:
        c["precio_segunda_unidad"] = segunda[0].valor
    nota = _NOTA_PRECIO.search(completo)
    c["nota_precio"] = re.sub(r"\s+", " ", nota.group(0)).strip() if nota else ""

    # --- promoción / condiciones ---
    promos = []
    for nombre, patron in PROMOCIONES:
        for m in patron.finditer(completo):
            etiqueta = re.sub(r"\s+", "", m.group(0)) if nombre in ("NxM", "Descuento %") else m.group(0).strip()
            etiqueta = etiqueta.replace("×", "x")
            if nombre == "NxM" and int(m.group(1)) <= int(m.group(2)):
                continue
            if etiqueta.lower() not in (p.lower() for p in promos):
                promos.append(etiqueta)
    if segunda and not any("unidad" in p.lower() for p in promos):
        promos.append(f"2ª unidad {segunda[0].valor:.2f} €")
    if cupones and not any("cup" in p.lower() for p in promos):
        promos.append(f"Cupón {c['cupon']:.2f} € próxima compra")
    c["promocion"] = "; ".join(promos)
    conds = []
    for m in CONDICIONES.finditer(completo):
        t = m.group(0).strip()
        if t.lower() not in (x.lower() for x in conds):
            conds.append(t)
    c["condiciones"] = "; ".join(conds)

    # --- descripción limpia ---
    descriptivas: list[tuple[Linea, str]] = []
    for l in ordenadas:
        t = _quitar_precios(l.texto)
        t = ETIQUETAS.sub(" ", t)
        for patron in [p for _, p in PROMOCIONES] + [CONDICIONES]:
            t = patron.sub(" ", t)
        t = re.sub(r"\s{2,}", " ", t).strip(" -–|:;,.")
        if t and not _RUIDO.match(t) and sum(ch.isalpha() for ch in t) >= 2:
            descriptivas.append((l, t))
    descripcion = " ".join(t for _, t in descriptivas)

    # --- formato ---
    formatos = []
    for m in FORMATO.finditer(descripcion):
        f = m.group(0).strip()
        if f.lower() not in (x.lower() for x in formatos):
            formatos.append(f)
    c["formato"] = ", ".join(formatos[:3])

    # --- marca y producto ---
    marca = _marca(descripcion, descriptivas)
    c["marca"] = marca
    # Si la marca es una línea suelta encima del producto, no se repite en el nombre
    producto = " ".join(t for _, t in descriptivas if not (t == marca and len(descriptivas) > 1))
    c["producto"] = producto[:300]
    c["texto_completo"] = completo

    # --- cálculos y alertas ---
    if not sello and c.get("precio_anterior") and c["precio_anterior"] > 0:
        c["descuento_pct"] = round((1 - of.precio.valor / c["precio_anterior"]) * 100, 1)
        if c["precio_anterior"] < of.precio.valor:
            of.alertas.append("Precio anterior menor que el de oferta")
    if sello:
        of.alertas.append("Oferta sin precio en el folleto (solo promoción)")
    if not producto:
        of.alertas.append("Precio sin descripción asociada")
    if len(producto) > 180:
        of.alertas.append("Descripción muy larga: posible mezcla de productos")
    if not of.precio.con_euro:
        of.alertas.append("Precio sin símbolo € (detectado por tamaño)")
    if of.precio.motor == "pdfplumber":
        of.alertas.append("Precio recuperado por pdfplumber")
    elif of.precio.motor == "ocr":
        of.alertas.append("Leído por OCR")
    of.campos = c
