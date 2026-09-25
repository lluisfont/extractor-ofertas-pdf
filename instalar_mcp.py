"""Registra el servidor MCP «extractor-ofertas» en Claude Desktop y en ChatGPT Desktop (Codex).

Uso:  python instalar_mcp.py            # instala en las apps que encuentre
      python instalar_mcp.py --quitar   # elimina el registro

Hace copia de seguridad (.bak) de cada archivo antes de modificarlo y no toca el resto
de servidores configurados. Reinicia la app después de ejecutarlo.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

NOMBRE = "extractor-ofertas"
LANZADOR = Path(__file__).resolve().parent / "mcp_servidor.py"
PYTHON = sys.executable


def _backup(ruta: Path) -> None:
    if ruta.exists():
        shutil.copy2(ruta, ruta.with_name(f"{ruta.name}.{datetime.now():%Y%m%d_%H%M%S}.bak"))


def rutas_claude() -> list[Path]:
    rutas = []
    appdata = os.environ.get("APPDATA")
    if appdata and Path(appdata, "Claude").exists():
        rutas.append(Path(appdata, "Claude", "claude_desktop_config.json"))
    local = os.environ.get("LOCALAPPDATA")
    if local:  # versión de Microsoft Store (MSIX)
        for pkg in Path(local, "Packages").glob("Claude_*"):
            carpeta = pkg / "LocalCache" / "Roaming" / "Claude"
            if carpeta.exists():
                rutas.append(carpeta / "claude_desktop_config.json")
    mac = Path.home() / "Library" / "Application Support" / "Claude"
    if mac.exists():
        rutas.append(mac / "claude_desktop_config.json")
    return rutas


def claude(ruta: Path, quitar: bool) -> str:
    datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() and ruta.stat().st_size else {}
    servidores = datos.setdefault("mcpServers", {})
    if quitar:
        if servidores.pop(NOMBRE, None) is None:
            return f"Claude Desktop: no estaba registrado ({ruta})"
    else:
        servidores[NOMBRE] = {"command": PYTHON, "args": [str(LANZADOR)]}
    _backup(ruta)
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    return f"Claude Desktop: {'eliminado de' if quitar else 'registrado en'} {ruta}"


def codex(quitar: bool) -> str | None:
    carpeta = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    if not carpeta.exists():
        return None
    ruta = carpeta / "config.toml"
    texto = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
    # Quita la sección anterior (si existe) hasta la siguiente cabecera [..]
    patron = re.compile(rf'^\[mcp_servers\.(?:"{NOMBRE}"|{NOMBRE})\]\n(?:(?!\[).*\n?)*', re.MULTILINE)
    nuevo = patron.sub("", texto).rstrip() + "\n"
    if not quitar:
        nuevo += (f'\n[mcp_servers.{NOMBRE}]\n'
                  f'command = {json.dumps(PYTHON)}\n'
                  f'args = [{json.dumps(str(LANZADOR))}]\n'
                  f'startup_timeout_sec = 30\n')
    _backup(ruta)
    ruta.write_text(nuevo, encoding="utf-8")
    return f"ChatGPT Desktop / Codex: {'eliminado de' if quitar else 'registrado en'} {ruta}"


def main() -> int:
    quitar = "--quitar" in sys.argv
    hechos = [claude(r, quitar) for r in rutas_claude()]
    c = codex(quitar)
    if c:
        hechos.append(c)
    if not hechos:
        print("No encuentro Claude Desktop ni ChatGPT/Codex instalados.")
        return 1
    print("\n".join(hechos))
    if not quitar:
        print("\nReinicia la app (ciérrala del todo, también de la bandeja del sistema) y pide en el chat:\n"
              "  «Procesa el folleto de la carpeta entrada con extractor-ofertas»")
    return 0


if __name__ == "__main__":
    sys.exit(main())
