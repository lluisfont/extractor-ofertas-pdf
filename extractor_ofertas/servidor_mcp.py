"""Servidor MCP para Claude Desktop y ChatGPT Desktop (Codex / Work).

El modelo del chat hace la interpretación visual de cada página; este servidor le
entrega la página, verifica lo que devuelve contra el texto real del PDF y genera el Excel.

Arranque:  python -m extractor_ofertas mcp            (stdio, lo lanza la app de escritorio)
           python -m extractor_ofertas mcp --http     (HTTP, para el túnel MCP de ChatGPT)
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer

from .config import Config
from .exportar import exportar
from .verificacion import (Folleto, OfertaEntrada, PrecioDescartado, Sesion, informe_texto,
                           resultado_desde_sesion, texto_para_modelo, verificar)

log = logging.getLogger(__name__)

from .criterios import INSTRUCCIONES  # noqa: E402  (única fuente de criterios)

mcp = MCPServer("extractor-ofertas", instructions=INSTRUCCIONES, version="0.2.0")
_cfg = Config.cargar()
_folletos: dict[str, Folleto] = {}


def _ruta(archivo: str) -> Path:
    nombre = Path(archivo).name
    for carpeta in (_cfg.carpeta_entrada, _cfg.carpeta_procesados):
        ruta = carpeta / nombre
        if ruta.exists():
            return ruta
    raise ValueError(f"No encuentro «{nombre}» en {_cfg.carpeta_entrada}. Usa listar_folletos.")


def _folleto(archivo: str) -> Folleto:
    ruta = _ruta(archivo)
    clave = str(ruta)
    if clave not in _folletos:
        _folletos[clave] = Folleto(ruta, _cfg)
    return _folletos[clave]


def _comprobar_pagina(f: Folleto, pagina: int) -> None:
    if not 1 <= pagina <= f.paginas:
        raise ValueError(f"El folleto tiene {f.paginas} páginas; la página {pagina} no existe.")


@mcp.tool()
def listar_folletos() -> str:
    """Lista los folletos PDF de la carpeta de entrada con su número de páginas y progreso."""
    _cfg.crear_carpetas()
    pdfs = sorted({p for p in _cfg.carpeta_entrada.iterdir() if p.suffix.lower() == ".pdf"})
    if not pdfs:
        return f"No hay folletos en {_cfg.carpeta_entrada}. Copia ahí el PDF."
    lineas = []
    for p in pdfs:
        f = _folleto(p.name)
        s = Sesion(p, _cfg, f.paginas)
        pend = s.pendientes()
        avisos = s.con_avisos()
        lineas.append(f"- {p.name}: {f.paginas} páginas, {f.paginas - len(pend)} procesadas"
                      + (f", pendientes: {_rangos(pend)}" if pend else ", todas procesadas")
                      + (f", con avisos: {_rangos(avisos)}" if avisos else ""))
    return "\n".join(lineas)


@mcp.tool()
def leer_pagina(archivo: str, pagina: int, incluir_imagen: bool = True) -> list:
    """Devuelve la imagen de una página del folleto, su capa de texto con coordenadas y la lista
    de precios detectados que deben quedar cubiertos por alguna oferta."""
    f = _folleto(archivo)
    _comprobar_pagina(f, pagina)
    texto = texto_para_modelo(f.analizar(pagina), f.paginas)
    if not incluir_imagen:
        return [texto]
    return [Image(data=f.imagen_png(pagina), format="png"), texto]


@mcp.tool()
def guardar_pagina(archivo: str, pagina: int, ofertas: list[OfertaEntrada],
                   precios_no_oferta: list[PrecioDescartado] | None = None,
                   vigencia_pagina: str | None = None) -> str:
    """Guarda TODAS las ofertas de una página (sustituye lo guardado antes para esa página),
    las verifica contra el texto del PDF y devuelve el informe de verificación."""
    f = _folleto(archivo)
    _comprobar_pagina(f, pagina)
    a = f.analizar(pagina)
    descartes = precios_no_oferta or []
    v = verificar(a, ofertas, descartes)
    s = Sesion(f.ruta, _cfg, f.paginas)
    s.guardar_pagina(pagina, ofertas, descartes, vigencia_pagina, v, a)
    pend = s.pendientes()
    siguiente = f"Siguiente página pendiente: {pend[0]}." if pend else "No quedan páginas pendientes: ya puedes llamar a generar_excel."
    return informe_texto(pagina, v, len(ofertas)) + "\n" + siguiente


@mcp.tool()
def estado_folleto(archivo: str) -> str:
    """Resumen del progreso: páginas pendientes, páginas con avisos y ofertas guardadas."""
    f = _folleto(archivo)
    s = Sesion(f.ruta, _cfg, f.paginas)
    total = sum(len(p["ofertas"]) for p in s.datos["paginas"].values())
    return (f"{f.ruta.name}: {f.paginas} páginas, {total} ofertas guardadas.\n"
            f"Pendientes: {_rangos(s.pendientes()) or 'ninguna'}\n"
            f"Con avisos: {_rangos(s.con_avisos()) or 'ninguna'}")


@mcp.tool()
def generar_excel(archivo: str, mover_pdf_a_procesados: bool = True) -> str:
    """Genera el Excel en la carpeta de salida con todas las ofertas guardadas y la auditoría
    (páginas pendientes, precios sin cubrir, importes no verificados)."""
    f = _folleto(archivo)
    s = Sesion(f.ruta, _cfg, f.paginas)
    res = resultado_desde_sesion(s, f)
    destino = exportar(res, _cfg.carpeta_salida)
    msg = [f"Excel generado: {destino}", f"Ofertas: {len(res.ofertas)} | Estado: {res.estado}"]
    pend = s.pendientes()
    if pend:
        msg.append(f"ATENCIÓN: faltan páginas por procesar ({_rangos(pend)}); figuran como ERROR en el Excel.")
    elif mover_pdf_a_procesados and f.ruta.parent == _cfg.carpeta_entrada:
        f.cerrar()
        _folletos.pop(str(f.ruta), None)
        _cfg.carpeta_procesados.mkdir(parents=True, exist_ok=True)
        dest_pdf = _cfg.carpeta_procesados / f.ruta.name
        if dest_pdf.exists():
            dest_pdf = dest_pdf.with_name(f"{f.ruta.stem}_{datetime.now():%Y%m%d_%H%M%S}.pdf")
        shutil.move(str(f.ruta), dest_pdf)
        msg.append(f"PDF movido a {dest_pdf.parent}")
    return "\n".join(msg)


@mcp.prompt()
def procesar_folleto(archivo: str = "") -> str:
    """Procesa un folleto completo de la carpeta de entrada y genera su Excel."""
    objetivo = f"el folleto «{archivo}»" if archivo else "el folleto que haya en la carpeta de entrada"
    return (f"Procesa {objetivo} con las herramientas de extractor-ofertas: empieza con listar_folletos, "
            "recorre todas las páginas pendientes (leer_pagina -> guardar_pagina, corrigiendo hasta que "
            "cada página quede VERIFICADA o VERIFICADA (OCR)) y termina con generar_excel. "
            "No me pidas confirmación entre páginas.")


def _rangos(nums: list[int]) -> str:
    if not nums:
        return ""
    tramos, ini, prev = [], nums[0], nums[0]
    for x in nums[1:] + [None]:
        if x is not None and x == prev + 1:
            prev = x
            continue
        tramos.append(str(ini) if ini == prev else f"{ini}-{prev}")
        if x is not None:
            ini = prev = x
    return ", ".join(tramos)


def main(http: bool = False, puerto: int = 8765) -> None:
    _cfg.crear_carpetas()
    # stdout es el canal MCP en stdio: el log va solo a archivo
    logging.basicConfig(level=logging.INFO, filename=_cfg.carpeta_logs / "mcp.log", encoding="utf-8",
                        format="%(asctime)s %(levelname)-7s %(message)s")
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    if http:
        mcp.run(transport="streamable-http", port=puerto)
    else:
        mcp.run()
