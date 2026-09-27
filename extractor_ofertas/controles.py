"""Controles cruzados del detector de precios, para calibrarlo con un folleto de una cadena nueva.

- «Nada se escapa»: todo importe «0,00» del texto bruto del PDF debe estar entre los precios detectados.
- «Nada se inventa»: todo precio detectado debe poder reconstruirse con trozos del texto bruto.

Las falsas alarmas típicas son formatos («1,25 L», «6,74 pulgadas»); todo lo demás es un fallo del
detector que hay que corregir antes de extraer el folleto. En folletos solo de imágenes no hay texto
bruto con el que comparar: se valida el OCR cotejando a mano un par de páginas.
"""
from __future__ import annotations

import re
from collections import Counter

from .verificacion import Folleto

_IMPORTE = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})*,\d{2})(?!\d)"
                      r"(?!\s*(?:%|cm|mm|kg\b|g\b|l\b|ml|cl|m\b|x\b|W\b|\"|”))")


def sin_detectar(f: Folleto) -> dict[int, dict[float, int]]:
    """Importes del texto bruto que no están entre los precios detectados, por página."""
    faltan = {}
    for n in range(1, f.paginas + 1):
        a = f.analizar(n)
        if a.fuente != "pdf":
            continue
        crudo = Counter(round(float(m.group(1).replace(".", "").replace(",", ".")), 2)
                        for m in _IMPORTE.finditer(a.texto_bruto))
        resto = crudo - Counter(round(p.valor, 2) for p in a.precios)
        if resto:
            faltan[n] = dict(resto)
    return faltan


def inventados(f: Folleto) -> list[tuple[int, float, str]]:
    """Precios detectados que no se pueden reconstruir con trozos del texto bruto."""
    malos = []
    for n in range(1, f.paginas + 1):
        a = f.analizar(n)
        if a.fuente != "pdf":
            continue
        t = a.texto_bruto
        fichas = set(re.findall(r"[\d.,'’]+", t))
        for p in a.precios:
            ent, cc = int(p.valor), round(p.valor * 100) % 100
            miles = f"{ent:,}".replace(",", ".")
            juntos = {f"{miles},{cc:02d}", f"{ent},{cc:02d}", f"{miles}.{cc:02d}", f"{ent}.{cc:02d}"}
            enteros = {str(ent), miles}
            ok = (any(j in t for j in juntos)
                  or (cc == 0 and any(re.search(rf"(?<![\d,.]){re.escape(e)}(?![\d,])", t) for e in enteros))
                  or ((f",{cc:02d}" in fichas or f"{cc:02d}" in fichas) and (enteros & fichas or f"{ent}," in fichas)))
            if not ok:
                malos.append((n, p.valor, p.linea.texto if p.linea else ""))
    return malos


def informe(f: Folleto) -> str:
    fuentes = Counter(f.analizar(n).fuente for n in range(1, f.paginas + 1))
    lineas = [f"{f.ruta.name}: {f.paginas} páginas ({', '.join(f'{v} {k}' for k, v in fuentes.items())})"]
    if fuentes.get("ocr") or fuentes.get("ninguna"):
        lineas.append("Hay páginas sin capa de texto: coteja a mano el OCR de un par de ellas con la imagen.")
    faltan = sin_detectar(f)
    lineas.append(f"Importes del texto sin detectar: {sum(sum(v.values()) for v in faltan.values())}")
    for n, v in faltan.items():
        lineas.append(f"  pág. {n}: " + ", ".join(f"{x:.2f}" + (f" (x{c})" if c > 1 else "") for x, c in v.items()))
    malos = inventados(f)
    lineas.append(f"Precios detectados que no se pueden reconstruir del texto: {len(malos)}")
    lineas += [f"  pág. {n}: {v:.2f} en «{t}»" for n, v, t in malos]
    return "\n".join(lineas)
