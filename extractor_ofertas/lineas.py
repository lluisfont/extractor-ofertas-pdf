"""Reconstrucción de líneas visuales a partir de palabras con coordenadas.

Solo se unen palabras que se solapan verticalmente y están cerca en horizontal,
de modo que las columnas y cuadrículas del folleto no se mezclan entre sí.
"""
from __future__ import annotations

import re

from .modelos import Linea, Palabra

_ENTERO = re.compile(r"^\d{1,4}[,.'’]?$")
_CENTIMOS = re.compile(r"^[,.'’]?\d{2}(€|,-|-)?$")


def _solape_vertical(a0, a1, b0, b1) -> float:
    inter = min(a1, b1) - max(a0, b0)
    menor = min(a1 - a0, b1 - b0) or 1
    return inter / menor


def construir_lineas(palabras: list[Palabra]) -> list[Linea]:
    lineas: list[list[Palabra]] = []
    for p in sorted(palabras, key=lambda w: (w.x0, w.y0)):
        mejor, mejor_solape = None, 0.0
        for grupo in lineas:
            # Referencia: la palabra más a la derecha de la línea que solapa en vertical con p
            # (así un "€" apilado bajo unos céntimos en superíndice se une al número grande).
            candidatas = [w for w in grupo if _solape_vertical(w.y0, w.y1, p.y0, p.y1) >= 0.5]
            if not candidatas:
                continue
            ref = max(candidatas, key=lambda w: w.x1)
            if p.x0 < grupo[-1].x0 - 0.3 * p.tamano:
                continue
            hueco = p.x0 - ref.x1
            menor, mayor = min(p.tamano, ref.tamano), max(p.tamano, ref.tamano)
            if mayor > 1.8 * menor:
                # Tamaños muy distintos: solo se unen las piezas de un precio (1 | 99 | €)
                pequeno = p if p.tamano < ref.tamano else ref
                if not (_CENTIMOS.match(pequeno.texto) or pequeno.texto in ("€", "€.")) or hueco > 0.25 * menor:
                    continue
            if hueco < -0.3 * mayor or hueco > 0.9 * menor:
                continue
            solape = _solape_vertical(ref.y0, ref.y1, p.y0, p.y1)
            if solape > mejor_solape:
                mejor, mejor_solape = grupo, solape
        if mejor is None:
            lineas.append([p])
        else:
            mejor.append(p)

    resultado = [_componer(_ordenar_apilados(g)) for g in lineas]
    resultado.sort(key=lambda l: (round(l.y0 / 3), l.x0))
    return resultado


def _ordenar_apilados(palabras: list[Palabra]) -> list[Palabra]:
    """En «16 €/,99» el € va encima de los céntimos: se coloca detrás para leer «16,99€»."""
    ps = list(palabras)
    for i in range(len(ps) - 1):
        a, b = ps[i], ps[i + 1]
        if a.texto in ("€", "€.") and _CENTIMOS.match(b.texto):
            solape = min(a.x1, b.x1) - max(a.x0, b.x0)
            if solape > 0.4 * min(a.x1 - a.x0, b.x1 - b.x0):
                ps[i], ps[i + 1] = b, a
    return ps


def _componer(palabras: list[Palabra]) -> Linea:
    """Une el texto de la línea. Detecta el patrón típico de folleto con euros
    grandes y céntimos pequeños en superíndice (1 99€ -> 1,99€)."""
    texto, tramos = "", []
    for i, p in enumerate(palabras):
        if i:
            ant = palabras[i - 1]
            hueco = p.x0 - ant.x1
            pegado = hueco < 0.15 * min(p.tamano, ant.tamano)
            es_centimo = (_ENTERO.match(ant.texto) and _CENTIMOS.match(p.texto)
                          and p.tamano < 0.85 * ant.tamano)
            if es_centimo and not re.search(r"[,.'’]$", ant.texto) and not re.match(r"^[,.'’]", p.texto):
                texto += ","
            elif not pegado:
                texto += " "
        ini = len(texto)
        texto += p.texto
        tramos.append((ini, len(texto)))
    return Linea(palabras=palabras, texto=texto, tramos=tramos)
