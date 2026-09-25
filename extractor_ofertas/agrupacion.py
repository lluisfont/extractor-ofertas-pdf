"""Agrupación espacial: cada precio principal es el ancla de una oferta y el resto
de textos y precios secundarios se asignan al ancla más cercana."""
from __future__ import annotations

import re
import statistics

from .modelos import Linea, Oferta, Precio

_SOLO_PRECIO = re.compile(r"^[\s\d.,'’€/a-z%-]*$", re.IGNORECASE)


def _dentro(caja, r, margen=2.0) -> bool:
    return caja.x0 >= r[0] - margen and caja.y0 >= r[1] - margen and caja.x1 <= r[2] + margen and caja.y1 <= r[3] + margen


def _separados(caja_texto, ancla: Precio, recuadros) -> bool:
    """True si algún recuadro dibujado contiene a uno de los dos pero no al otro."""
    for r in recuadros:
        if _dentro(caja_texto, r) != _dentro(ancla.caja, r):
            return True
    return False


def _distancia(caja_texto, ancla: Precio, cfg, recuadros=()) -> float:
    a = ancla.caja
    dx = max(0.0, max(a.x0 - caja_texto.x1, caja_texto.x0 - a.x1))
    dy = max(0.0, max(a.y0 - caja_texto.y1, caja_texto.y0 - a.y1))
    if caja_texto.y0 >= a.y1 - 1:  # el texto está debajo del precio
        dy *= cfg.penalizacion_texto_debajo
    d = (dx * dx * 2.25 + dy * dy) ** 0.5  # la distancia horizontal pesa más (columnas)
    if recuadros and _separados(caja_texto, ancla, recuadros):
        d = d * 4 + 50
    return d


def es_cabecera(linea: Linea, mediana: float) -> bool:
    letras = [c for c in linea.texto if c.isalpha()]
    return (len(letras) >= 4 and linea.tamano >= 1.3 * mediana and all(c.isupper() for c in letras)
            and len(linea.texto.split()) <= 5 and not any(c.isdigit() for c in linea.texto))


def agrupar(lineas: list[Linea], precios: list[Precio], pagina: int, cfg, siguiente_id: int,
            recuadros=(), excluir=()):
    tamanos = [p.tamano for l in lineas for p in l.palabras] or [10.0]
    mediana = statistics.median(tamanos)

    anclas = [p for p in precios if p.tipo == "principal"]
    anclas.sort(key=lambda p: (round(p.y0 / 5), p.x0))
    ofertas = []
    for i, a in enumerate(anclas):
        of = Oferta(id=siguiente_id + i, pagina=pagina, precio=a)
        a.oferta_id = of.id
        ofertas.append(of)

    cabeceras = [l for l in lineas if es_cabecera(l, mediana)]
    lineas_precio = {id(p.linea) for p in precios}
    sin_asignar: list[Linea] = []
    huerfanos: list[Precio] = []

    if not ofertas:
        return ofertas, [l for l in lineas if l not in cabeceras], [p for p in precios], cabeceras

    for linea in lineas:
        if linea in cabeceras:
            continue
        if any(patron.search(linea.texto) for patron in excluir):
            sin_asignar.append(linea)
            continue
        # Una línea que solo contiene el precio ancla ya está representada por él
        if id(linea) in lineas_precio and _SOLO_PRECIO.match(linea.texto) and \
                any(p.linea is linea and p.tipo == "principal" for p in precios):
            of = next(o for o in ofertas if o.precio.linea is linea)
            of.lineas.append(linea)
            continue
        caja = linea.caja
        mejor = min(ofertas, key=lambda o: _distancia(caja, o.precio, cfg, recuadros))
        radio = max(cfg.radio_asociacion_minimo, cfg.radio_asociacion_factor * mejor.precio.tamano)
        if _distancia(caja, mejor.precio, cfg, recuadros) <= radio:
            mejor.lineas.append(linea)
        else:
            sin_asignar.append(linea)

    for p in precios:
        if p.tipo == "principal":
            continue
        mejor = min(ofertas, key=lambda o: _distancia(p.caja, o.precio, cfg, recuadros))
        radio = max(cfg.radio_asociacion_minimo, cfg.radio_asociacion_factor * mejor.precio.tamano)
        if _distancia(p.caja, mejor.precio, cfg, recuadros) <= radio:
            mejor.secundarios.append(p)
            p.oferta_id = mejor.id
        else:
            huerfanos.append(p)

    for of in ofertas:
        of.lineas.sort(key=lambda l: (round(l.y0 / 3), l.x0))
        of.seccion = _seccion(of, cabeceras)
    return ofertas, sin_asignar, huerfanos, cabeceras


def _seccion(of: Oferta, cabeceras: list[Linea]) -> str:
    candidatas = [c for c in cabeceras if c.y1 <= of.precio.y0]
    if not candidatas:
        return ""
    # la cabecera más cercana por encima que empieza a la izquierda del precio
    def clave(c):
        return (0 if c.x0 <= of.precio.caja.cx else 1, of.precio.y0 - c.y1)
    return min(candidatas, key=clave).texto.strip()
