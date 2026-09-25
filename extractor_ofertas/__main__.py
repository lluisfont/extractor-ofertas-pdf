"""Uso:
    python -m extractor_ofertas mcp             # servidor MCP para Claude Desktop / ChatGPT Desktop
    python -m extractor_ofertas mcp --http      # igual, por HTTP (túnel MCP de ChatGPT)
    python -m extractor_ofertas procesar X.pdf  # borrador sin IA, por reglas
    python -m extractor_ofertas vigilar         # borrador sin IA de cada PDF que llegue a entrada/
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Config
from .exportar import exportar
from .procesador import procesar_pdf
from .vigilante import vigilar


def _logging(cfg: Config) -> None:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    cfg.carpeta_logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(cfg.carpeta_logs / "extractor.log", encoding="utf-8")])
    logging.getLogger("pdfminer").setLevel(logging.ERROR)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="extractor_ofertas", description="Extrae ofertas de folletos PDF a Excel.")
    ap.add_argument("--config", type=Path, help="Ruta a config.json")
    sub = ap.add_subparsers(dest="orden")
    pm = sub.add_parser("mcp", help="Servidor MCP para Claude Desktop / ChatGPT Desktop")
    pm.add_argument("--http", action="store_true", help="Transporte HTTP en lugar de stdio")
    pm.add_argument("--puerto", type=int, default=8765)
    sub.add_parser("vigilar", help="Borrador sin IA de cada PDF que llegue a entrada/")
    pp = sub.add_parser("procesar", help="Procesa PDFs concretos")
    pp.add_argument("pdfs", nargs="+", type=Path)
    pp.add_argument("--salida", type=Path, help="Carpeta de salida (por defecto la configurada)")
    args = ap.parse_args(argv)

    if args.orden == "mcp":
        from .servidor_mcp import main as servidor
        servidor(http=args.http, puerto=args.puerto)  # sin log a stdout: es el canal MCP
        return 0

    cfg = Config.cargar(args.config)
    _logging(cfg)
    if args.orden == "procesar":
        ok = True
        for pdf in args.pdfs:
            res = procesar_pdf(pdf, cfg)
            destino = exportar(res, args.salida or cfg.carpeta_salida)
            logging.info("%s -> %s | %d ofertas | %s", pdf.name, destino, len(res.ofertas), res.estado)
            ok &= "errores" not in res.estado
        return 0 if ok else 1
    vigilar(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
