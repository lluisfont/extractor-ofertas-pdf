"""Uso:
    python -m extractor_ofertas                 # vigila la carpeta entrada/
    python -m extractor_ofertas procesar X.pdf  # procesa uno o varios PDFs sin moverlos
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
    sub.add_parser("vigilar", help="Vigila la carpeta de entrada (por defecto)")
    pp = sub.add_parser("procesar", help="Procesa PDFs concretos")
    pp.add_argument("pdfs", nargs="+", type=Path)
    pp.add_argument("--salida", type=Path, help="Carpeta de salida (por defecto la configurada)")
    args = ap.parse_args(argv)

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
