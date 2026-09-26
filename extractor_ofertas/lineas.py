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
            grande = max(candidatas, key=lambda w: w.tamano)
            if grande.tamano > 1.8 * p.tamano:
                # p es mucho más pequeña que el número de la línea: solo puede ser una pieza del precio
                # (céntimos, «€», «€/ud», coma). Se mide contra el número grande, no contra otra pieza.
                pieza = ((_CENTIMOS.match(p.texto) and p.tamano >= 0.3 * grande.tamano)  # no «50 cl» dentro del 6
                         or p.texto.startswith("€") or p.texto in (",", ".", "'", "’"))
                dentro = p.y0 >= grande.y0 - 0.1 * grande.alto and p.y1 <= grande.y1 + 0.1 * grande.alto
                if not (pieza and dentro):
                    continue
                if p.texto.startswith("€"):
                    if p.x0 < grande.x1 - 0.12 * grande.tamano:
                        continue  # unidad que empieza dentro de la caja del número: es texto de debajo
                elif p.x0 < grande.x1 - 0.25 * grande.tamano:
                    continue  # los céntimos van a la derecha del número (arriba o abajo según la cadena)
                if p.x0 - max(w.x1 for w in grupo) > 0.5 * p.tamano:
                    continue  # demasiado lejos de lo último del precio
                hueco = 0.0
                menor = mayor = p.tamano
                es_pieza = True
            else:
                es_pieza = False
                if _CENTIMOS.match(p.texto):
                    # unos céntimos se miden contra el número, no contra una pieza «€…» apilada ya unida
                    ref = max((w for w in candidatas if not w.texto.startswith("€")), key=lambda w: w.x1, default=ref)
                hueco = p.x0 - ref.x1
                menor, mayor = min(p.tamano, ref.tamano), max(p.tamano, ref.tamano)
                if mayor > 1.8 * menor:
                    continue  # un número grande nunca continúa una línea de letra pequeña
            if hueco < -0.3 * mayor or hueco > 0.9 * menor:
                continue
            solape = _solape_vertical(ref.y0, ref.y1, p.y0, p.y1)
            if es_pieza:
                solape -= 0.5  # a igualdad, gana la línea de su mismo tamaño («2 uds: 5,18 €/kg»)
            if mejor is None or solape > mejor_solape:
                mejor, mejor_solape = grupo, solape
        if mejor is None:
            lineas.append([p])
        else:
            mejor.append(p)

    resultado = [_componer(_ordenar_apilados(g)) for g in lineas]
    resultado.sort(key=lambda l: (round(l.y0 / 3), l.x0))
    return resultado


def _ordenar_apilados(palabras: list[Palabra]) -> list[Palabra]:
    """Piezas apiladas del precio: «€», «€/ud» o «€/kg» encima o debajo de los céntimos se
    colocan detrás para leer «16,99€» o «6,80€/L»."""
    # Las piezas «€…» se ordenan por donde terminan: quedan detrás de los céntimos apilados
    # («20 €/par ,99» -> «20,99€/par») sin alterar el orden del texto normal.
    return sorted(palabras, key=lambda w: w.x1 if w.texto.startswith("€") else w.x0)


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
                          and 0.3 * ant.tamano <= p.tamano < 0.85 * ant.tamano
                          and p.y0 >= ant.y0 - 0.1 * ant.alto)  # en superíndice, no un precio encima
            dos_numeros = ant.texto[-1:].isdigit() and p.texto[:1].isdigit()
            if es_centimo and not re.search(r"[,.'’]$", ant.texto) and not re.match(r"^[,.'’]", p.texto):
                texto += ","
            elif not pegado or dos_numeros:
                texto += " "  # «3x2» + «0,83» no debe leerse «3x20,83»
        ini = len(texto)
        texto += p.texto
        tramos.append((ini, len(texto)))
    return Linea(palabras=palabras, texto=texto, tramos=tramos)
