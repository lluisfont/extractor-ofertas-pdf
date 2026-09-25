"""Vigila la carpeta de entrada y procesa cada PDF nuevo en cuanto termina de copiarse."""
from __future__ import annotations

import logging
import queue
import shutil
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import Config
from .exportar import exportar
from .procesador import procesar_pdf

log = logging.getLogger(__name__)


def esperar_copia_completa(ruta: Path, timeout: float = 300) -> bool:
    """Espera a que el archivo deje de crecer y se pueda abrir en exclusiva."""
    inicio, tamano_prev, estables = time.time(), -1, 0
    while time.time() - inicio < timeout:
        if not ruta.exists():
            return False
        tamano = ruta.stat().st_size
        if tamano == tamano_prev and tamano > 0:
            estables += 1
            if estables >= 2:
                try:
                    with open(ruta, "rb+"):
                        return True
                except OSError:
                    pass  # todavía bloqueado por el proceso que copia
        else:
            estables = 0
        tamano_prev = tamano
        time.sleep(1)
    return False


def _mover(ruta: Path, carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / ruta.name
    if destino.exists():
        destino = carpeta / f"{ruta.stem}_{datetime.now():%Y%m%d_%H%M%S}{ruta.suffix}"
    shutil.move(str(ruta), destino)
    return destino


def procesar_archivo(ruta: Path, cfg: Config) -> Path | None:
    log.info("Procesando %s", ruta.name)
    t0 = time.time()
    try:
        res = procesar_pdf(ruta, cfg)
        salida = exportar(res, cfg.carpeta_salida)
    except Exception:
        log.error("Error procesando %s:\n%s", ruta.name, traceback.format_exc())
        if cfg.mover_pdf_tras_procesar:
            destino = _mover(ruta, cfg.carpeta_errores)
            destino.with_suffix(".error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        return None
    log.info("OK %s -> %s | %d ofertas | %s | %.1fs", ruta.name, salida.name, len(res.ofertas),
             res.estado, time.time() - t0)
    if cfg.mover_pdf_tras_procesar:
        _mover(ruta, cfg.carpeta_procesados)
    return salida


class _Manejador(FileSystemEventHandler):
    def __init__(self, cola: queue.Queue):
        self.cola = cola

    def _encolar(self, ruta: str):
        p = Path(ruta)
        if p.suffix.lower() == ".pdf":
            self.cola.put(p)

    def on_created(self, event):
        if not event.is_directory:
            self._encolar(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._encolar(event.dest_path)


def vigilar(cfg: Config) -> None:
    cfg.crear_carpetas()
    cola: queue.Queue[Path] = queue.Queue()
    for p in sorted(cfg.carpeta_entrada.glob("*.pdf")) + sorted(cfg.carpeta_entrada.glob("*.PDF")):
        cola.put(p)  # PDFs que ya estaban antes de arrancar

    pendientes: set[Path] = set()

    def trabajador():
        while True:
            ruta = cola.get()
            if ruta in pendientes:
                continue
            pendientes.add(ruta)
            try:
                if esperar_copia_completa(ruta):
                    procesar_archivo(ruta, cfg)
            finally:
                pendientes.discard(ruta)

    threading.Thread(target=trabajador, daemon=True).start()
    observador = Observer()
    observador.schedule(_Manejador(cola), str(cfg.carpeta_entrada), recursive=False)
    observador.start()
    log.info("Vigilando %s  (Ctrl+C para salir)", cfg.carpeta_entrada)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Deteniendo vigilante...")
    finally:
        observador.stop()
        observador.join()
