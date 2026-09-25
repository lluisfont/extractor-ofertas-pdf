"""Lanzador del servidor MCP para las apps de escritorio (no depende del directorio de trabajo)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extractor_ofertas.servidor_mcp import main  # noqa: E402

if __name__ == "__main__":
    main(http="--http" in sys.argv)
