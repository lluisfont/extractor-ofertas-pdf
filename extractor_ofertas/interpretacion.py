"""Interpretación de cada bloque de oferta: producto, formato, promoción, precios..."""
from __future__ import annotations

import re

from .modelos import Oferta
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
    r"en\s+tu\s+próxima\s+compra|acumula[\w\s]{0,20})", re.IGNORECASE)
FORMATO = re.compile(
    r"(?:pack\s+(?:de\s+)?\d+\s*(?:x\s*\d+(?:[.,]\d+)?\s*(?:cl|ml|l|g|gr|kg))?|"
    r"\d+\s?x\s?\d+(?:[.,]\d+)?\s?(?:cl|ml|l|g|gr|kg)\b|"
    r"\d+(?:[.,]\d+)?\s?(?:kg|g|gr|grs|l|lt|litros?|ml|cl|uds?|unidades|lavados|rollos|dosis|capsulas|cápsulas|m)\b|"
    r"bandeja|granel|al\s+corte|pieza|malla\s+\d+(?:[.,]\d+)?\s?kg)", re.IGNORECASE)
_RUIDO = re.compile(r"^[\s€/.,:;*+\-–()%]*$")


def _quitar_precios(texto: str) -> str:
    def rep(m):
        return "" if (m.group("cent") or (m.group("eur") and m.group("eur").strip())) else m.group(0)
    t = PATRON_PRECIO.sub(rep, texto)
    t = re.sub(r"(?:€|eur(?:os)?)?\s*/\s*(?:kg|l|ud|kilo|litro)\b", "", t, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", t).strip()


def interpretar(of: Oferta) -> None:
    textos = [l.texto.strip() for l in of.lineas]
    completo = " | ".join(t for t in textos if t)
    c: dict = {}

    # --- precios ---
    c["precio_oferta"] = of.precio.valor
    anteriores = [p for p in of.secundarios if p.tipo == "anterior"]
    otros = [p for p in of.secundarios if p.tipo == "secundario" and p.valor > of.precio.valor]
    if anteriores or otros:
        c["precio_anterior"] = max((anteriores or otros), key=lambda p: p.tamano).valor
    unitarios = [p for p in of.secundarios if p.tipo == "unitario"]
    if of.precio.tipo == "unitario":
        unitarios.insert(0, of.precio)
    if unitarios:
        c["precio_unitario"] = unitarios[0].valor
        c["unidad_precio_unitario"] = "€/" + unitarios[0].unidad
    segunda = [p for p in of.secundarios if p.tipo == "segunda_unidad"]
    if segunda:
        c["precio_segunda_unidad"] = segunda[0].valor

    # --- promoción / condiciones ---
    promos = []
    for nombre, patron in PROMOCIONES:
        for m in patron.finditer(completo):
            etiqueta = m.group(0).strip()
            if nombre == "NxM" and int(m.group(1)) <= int(m.group(2)):
                continue
            if etiqueta.lower() not in (p.lower() for p in promos):
                promos.append(etiqueta)
    if segunda and not any("unidad" in p.lower() for p in promos):
        promos.append(f"2ª unidad {segunda[0].valor:.2f} €")
    c["promocion"] = "; ".join(promos)
    conds = []
    for m in CONDICIONES.finditer(completo):
        t = m.group(0).strip()
        if t.lower() not in (x.lower() for x in conds):
            conds.append(t)
    c["condiciones"] = "; ".join(conds)

    # --- formato ---
    formatos = []
    for m in FORMATO.finditer(" ".join(textos)):
        f = m.group(0).strip()
        if f.lower() not in (x.lower() for x in formatos):
            formatos.append(f)
    c["formato"] = ", ".join(formatos[:3])

    # --- producto y marca ---
    descriptivas = []
    for l in of.lineas:
        t = _quitar_precios(l.texto)
        for patron in [p for _, p in PROMOCIONES] + [CONDICIONES]:
            t = patron.sub("", t)
        t = re.sub(r"\b(antes|ahora|pvp|precio|el kg|el litro|la unidad)\b\s*:?", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s{2,}", " ", t).strip(" -–|:;,.")
        if t and not _RUIDO.match(t) and sum(ch.isalpha() for ch in t) >= 2:
            descriptivas.append((l, t))

    marca = ""
    if len(descriptivas) >= 2:
        for l, t in descriptivas[:2]:
            letras = [ch for ch in t if ch.isalpha()]
            if letras and all(ch.isupper() for ch in letras) and len(t.split()) <= 3:
                otros_sizes = [x.tamano for x, _ in descriptivas if x is not l]
                if any(ch.islower() for _, tt in descriptivas if tt != t for ch in tt) or \
                        (otros_sizes and abs(l.tamano - max(otros_sizes)) > 0.5):
                    marca = t
                    break
    c["marca"] = marca
    producto = " ".join(t for l, t in descriptivas if t != marca)
    c["producto"] = producto[:300]
    c["texto_completo"] = completo

    # --- cálculos y alertas ---
    if c.get("precio_anterior") and c["precio_anterior"] > 0:
        c["descuento_pct"] = round((1 - of.precio.valor / c["precio_anterior"]) * 100, 1)
        if c["precio_anterior"] < of.precio.valor:
            of.alertas.append("Precio anterior menor que el de oferta")
    if not producto:
        of.alertas.append("Precio sin descripción asociada")
    if len(producto) > 180:
        of.alertas.append("Descripción muy larga: posible mezcla de productos")
    if not of.precio.con_euro:
        of.alertas.append("Precio sin símbolo € (detectado por tamaño)")
    if of.precio.motor != "pymupdf":
        of.alertas.append(f"Precio recuperado por {of.precio.motor}")
    of.campos = c
