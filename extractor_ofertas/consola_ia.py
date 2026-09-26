"""Las mismas herramientas del servidor MCP, por línea de comandos (para agentes como Claude Code).

    python -m extractor_ofertas.consola_ia leer    <pdf> <pagina> <salida.png>
    python -m extractor_ofertas.consola_ia guardar <pdf> <pagina> <ofertas.json>
    python -m extractor_ofertas.consola_ia estado  <pdf>
    python -m extractor_ofertas.consola_ia excel   <pdf>

ofertas.json: {"ofertas": [...], "precios_no_oferta": [{"id": "P3", "motivo": "..."}], "vigencia_pagina": null}
con los campos de OfertaEntrada (ver verificacion.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .config import Config
from .exportar import exportar
from .verificacion import (Folleto, OfertaEntrada, PrecioDescartado, Sesion, informe_texto,
                           resultado_desde_sesion, texto_para_modelo, verificar)


def main(argv: list[str]) -> int:
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8")
    orden, pdf = argv[0], Path(argv[1])
    cfg = Config.cargar()
    f = Folleto(pdf, cfg)
    s = Sesion(pdf, cfg, f.paginas)
    if orden == "leer":
        n, png = int(argv[2]), Path(argv[3])
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(f.imagen_png(n))
        print(texto_para_modelo(f.analizar(n), f.paginas))
    elif orden == "guardar":
        n = int(argv[2])
        datos = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
        ofertas = [OfertaEntrada(**o) for o in datos.get("ofertas", [])]
        descartes = [PrecioDescartado(**d) for d in datos.get("precios_no_oferta", [])]
        a = f.analizar(n)
        v = verificar(a, ofertas, descartes)
        s.guardar_pagina(n, ofertas, descartes, datos.get("vigencia_pagina"), v, a)
        print(informe_texto(n, v, len(ofertas)))
    elif orden == "estado":
        print(f"Pendientes: {s.pendientes()}\nCon avisos: {s.con_avisos()}")
    elif orden == "excel":
        destino = exportar(resultado_desde_sesion(s, f), cfg.carpeta_salida)
        print(destino)
    f.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
