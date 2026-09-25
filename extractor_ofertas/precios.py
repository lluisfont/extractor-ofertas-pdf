"""Detección y clasificación de precios dentro de las líneas visuales."""
from __future__ import annotations

import re
import statistics

from .modelos import Caja, Linea, Precio

# 1,99 € | 1.99€ | 1'99 | 1.234,50 € | 12 € | 0,99 EUR
PATRON_PRECIO = re.compile(
    r"(?<![\d,.'’/])"
    r"(?P<ent>\d{1,3}(?:\.\d{3})+|\d{1,4})"
    r"(?:\s?[,.'’]\s?(?P<cent>\d{2})(?!\d))?"
    r"(?P<eur>\s*(?:€|eur(?:os?)?\b|,-))?",
    re.IGNORECASE,
)
# Patrón simple para el conteo bruto de control (como el sugerido en la auditoría)
PATRON_EURO_BRUTO = re.compile(r"\d+\s?[,.'’]\s?\d{2}\s*€|\d+\s*€")

_UNIDAD_TRAS = re.compile(
    r"^\s*(?:€|eur(?:os?)?)?\s*(?:/|el|la|por|x)\s*"
    r"(?P<u>kg|kilo|g|100\s?g|l|litro|lt|100\s?ml|ml|ud|unidad|u|m|metro|docena|lavado|dosis|rollo|par)\b",
    re.IGNORECASE)
_UNIDADES_PU = r"kg|kilo|litro|l|100\s?g|100\s?ml|metro|m2|m|lavado|dosis|rollo|toallita|c[aá]psula"
_UNIDAD_ANTES = re.compile(
    rf"(?:el|la|por|/)\s*(?P<u>{_UNIDADES_PU})\.?\s*(?:sale\s+a|:|=)?\s*(?:\(\d\)\s*)?$", re.IGNORECASE)
_TOTAL_ANTES = re.compile(r"(?P<n>[2-9]|\d{2})\s*(?:unidades|uds\.?|packs|latas|botellas|bandejas)\s*:?\s*$",
                          re.IGNORECASE)
_NORMAL_ANTES = re.compile(r"(?<!\d)1\s*(?:unidad|ud\.?|pack|lata|botella|bandeja|paquete|bolsa|caja)\s*:?\s*$",
                           re.IGNORECASE)
_CUPON_ANTES = re.compile(r"cup[oó]n(?:\s+de)?(?:\s+descuento(?:\s+de)?)?\s*:?\s*$", re.IGNORECASE)
_CONDICION_ANTES = re.compile(
    r"(importe|m[aá]ximo|m[ií]nimo|superior\s+a|a\s+partir\s+de|hasta|comisi[oó]n|coste|adeudado|financ|cuota|"
    r"t\.?a\.?e|t\.?i\.?n|intereses|plazo|compras?\s+de)[^€]{0,45}$", re.IGNORECASE)
_MEDIDA_TRAS = re.compile(r"^\s*(?:x\s*\d|kg\b|g\b|gr\b|grs?\b|ml\b|cl\b|l\b|lt\b|%|cm\b|mm\b|m\b|w\b|v\b|uds?\b|"
                          r"unidades\b|lavados\b|rollos\b|capas\b|º|ª|h\b|min\b|años?\b|meses\b|pulgadas|\")",
                          re.IGNORECASE)
_ANTERIOR_ANTES = re.compile(r"(antes|pvp|p\.v\.p\.?|precio\s+anterior|precio\s+habitual|habitual)\s*:?\s*$",
                             re.IGNORECASE)
_SEGUNDA_ANTES = re.compile(r"(2\s?[ªa]|segunda)\s*(unidad|ud\.?)?\s*[:a]?\s*$", re.IGNORECASE)
_FECHA_CONTEXTO = re.compile(r"(del|al|hasta|desde|válid[oa]|valid[oa]|oferta)\s*(el\s*)?$", re.IGNORECASE)
_FECHA_TRAS = re.compile(r"^\s*[./-]\s*\d{2,4}")


def _normalizar_unidad(u: str) -> str:
    u = u.lower().replace(" ", "")
    return {"kilo": "kg", "litro": "l", "lt": "l", "unidad": "ud", "u": "ud", "metro": "m"}.get(u, u)


def _linea_superior(linea: Linea, caja: Caja, lineas: list[Linea]) -> Linea | None:
    """Línea inmediatamente encima del precio (etiquetas tipo «Cupón de», «El kg sale a»)."""
    mejor = None
    for l in lineas:
        if l is linea or l.y1 > caja.y0 + 0.3 * caja.alto or l.y1 < caja.y0 - 1.5 * max(l.tamano, 6):
            continue
        if min(l.x1, caja.x1 + 10) - max(l.x0, caja.x0 - 10) <= 0:
            continue
        if mejor is None or l.y1 > mejor.y1:
            mejor = l
    return mejor


def detectar_precios(lineas: list[Linea], pagina: int, cfg, motor: str = "pymupdf") -> list[Precio]:
    tamanos = [p.tamano for l in lineas for p in l.palabras]
    mediana = statistics.median(tamanos) if tamanos else 10.0
    precios: list[Precio] = []
    for linea in lineas:
        t = linea.texto
        previo: Precio | None = None
        fin_previo = 0
        for m in PATRON_PRECIO.finditer(t):
            ent, cent, eur = m.group("ent"), m.group("cent"), m.group("eur")
            con_euro = bool(eur and eur.strip())
            if not cent and not con_euro:
                continue  # un entero sin € no es un precio
            antes, despues = t[:m.start()], t[m.end():]
            palabras = linea.palabras_en(m.start(), m.end())
            if not palabras:
                continue
            tamano = max(p.tamano for p in palabras)
            caja = Caja.de(palabras)

            if not con_euro:
                if _MEDIDA_TRAS.match(despues) or _FECHA_TRAS.match(despues) or _FECHA_CONTEXTO.search(antes):
                    continue
                if tamano < cfg.factor_tamano_precio_sin_euro * mediana and not _UNIDAD_TRAS.match(despues):
                    continue
            try:
                valor = float(ent.replace(".", "") + "." + (cent or "00"))
            except ValueError:
                continue
            if valor <= 0 or valor > 100000:
                continue

            p = Precio(valor=valor, texto=m.group(0).strip(), caja=caja, tamano=tamano,
                       pagina=pagina, con_euro=con_euro, motor=motor, linea=linea,
                       confianza="alta" if con_euro else "media")
            contexto = antes
            if not antes.strip():
                sup = _linea_superior(linea, caja, lineas)
                contexto = sup.texto if sup else ""
            entre = t[fin_previo:m.start()]
            mu = _UNIDAD_TRAS.match(despues) or _UNIDAD_ANTES.search(contexto)
            mt = _TOTAL_ANTES.search(contexto)
            if previo is not None and previo.tipo == "unitario" and not entre.strip(" €"):
                p.tipo, p.unidad = "unitario", previo.unidad  # «El kg 17,69€ 16,95€»
            elif mu:
                p.tipo, p.unidad = "unitario", _normalizar_unidad(mu.group("u"))
            elif _CUPON_ANTES.search(contexto):
                p.tipo = "cupon"
            elif mt:
                p.tipo, p.unidad = "total", f"{mt.group('n')} uds"
            elif _NORMAL_ANTES.search(contexto) or _ANTERIOR_ANTES.search(contexto):
                p.tipo = "anterior"
            elif _SEGUNDA_ANTES.search(contexto):
                p.tipo = "segunda_unidad"
            elif _CONDICION_ANTES.search(contexto):
                p.tipo = "condicion"
            precios.append(p)
            previo, fin_previo = p, m.end()
    return precios


def marcar_tachados(precios: list[Precio], segmentos) -> None:
    for p in precios:
        c = p.caja
        for x0, y0, x1, y1 in segmentos:
            sx0, sx1 = min(x0, x1), max(x0, x1)
            solape = min(sx1, c.x1) - max(sx0, c.x0)
            if solape < 0.6 * c.ancho:
                continue
            # altura del segmento en el centro del precio
            if x1 != x0:
                y = y0 + (y1 - y0) * ((c.cx - x0) / (x1 - x0))
            else:
                continue
            if c.y0 + 0.2 * c.alto <= y <= c.y1 - 0.2 * c.alto:
                p.tachado = True
                if p.tipo in ("principal", "secundario"):
                    p.tipo = "anterior"
                break


def clasificar_por_tamano(precios: list[Precio], cfg) -> None:
    """Un precio 'principal' mucho más pequeño que otro precio cercano pasa a secundario."""
    principales = [p for p in precios if p.tipo == "principal"]
    for p in principales:
        for q in principales:
            if q is p or q.tamano <= p.tamano:
                continue
            radio = 5 * q.tamano
            dx = max(0, max(q.x0 - p.x1, p.x0 - q.x1))
            dy = max(0, max(q.y0 - p.y1, p.y0 - q.y1))
            if dx <= radio and dy <= radio and p.tamano < cfg.factor_precio_secundario * q.tamano:
                p.tipo = "secundario"
                break


def mismo_precio(a: Precio, b: Precio, tolerancia: float = 6.0) -> bool:
    return (abs(a.valor - b.valor) < 0.005 and abs(a.caja.cx - b.caja.cx) < tolerancia + a.caja.ancho / 2
            and abs(a.caja.cy - b.caja.cy) < tolerancia + a.caja.alto / 2)
