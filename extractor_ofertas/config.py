"""Configuración del extractor. Los valores por defecto se pueden sobrescribir
con un archivo config.json en la raíz del proyecto (mismas claves)."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field, fields
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    carpeta_entrada: Path = RAIZ / "entrada"
    carpeta_salida: Path = RAIZ / "salida"
    carpeta_procesados: Path = RAIZ / "procesados"
    carpeta_errores: Path = RAIZ / "errores"
    carpeta_logs: Path = RAIZ / "logs"

    # Mover el PDF a "procesados" (o "errores") al terminar
    mover_pdf_tras_procesar: bool = True

    # --- Detección de precios ---
    # Un número tipo 1,99 sin símbolo € se acepta como precio si su letra es
    # al menos este múltiplo del tamaño de letra mediano de la página.
    factor_tamano_precio_sin_euro: float = 1.6
    # Un precio cercano con letra más pequeña que esta fracción del precio
    # principal se considera secundario (precio/kg, precio anterior...).
    factor_precio_secundario: float = 0.6

    # --- Agrupación espacial ---
    # Distancia máxima (en puntos PDF) entre un texto y el precio al que se asocia,
    # expresada como múltiplo del tamaño de letra del precio (con un mínimo absoluto).
    radio_asociacion_factor: float = 7.0
    radio_asociacion_minimo: float = 110.0
    # Penalización para textos situados debajo del precio (suelen ser de la oferta de abajo).
    penalizacion_texto_debajo: float = 2.0

    # --- OCR ---
    ocr_activo: bool = True
    ocr_idioma: str = "spa"
    ocr_dpi: int = 300
    ocr_confianza_minima: int = 45
    tesseract_cmd: str = ""  # vacío = autodetectar
    # Si la página tiene menos de N palabras de texto real se lanza OCR.
    ocr_umbral_palabras: int = 15

    # --- Triangulación ---
    triangulacion_pdfplumber: bool = True

    extra: dict = field(default_factory=dict)

    @classmethod
    def cargar(cls, ruta: Path | None = None) -> "Config":
        cfg = cls()
        ruta = ruta or (RAIZ / "config.json")
        if ruta.exists():
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            nombres = {f.name: f for f in fields(cls)}
            for clave, valor in datos.items():
                if clave in nombres:
                    actual = getattr(cfg, clave)
                    setattr(cfg, clave, Path(valor) if isinstance(actual, Path) else valor)
                else:
                    cfg.extra[clave] = valor
        return cfg

    def crear_carpetas(self) -> None:
        for p in (self.carpeta_entrada, self.carpeta_salida, self.carpeta_procesados,
                  self.carpeta_errores, self.carpeta_logs):
            p.mkdir(parents=True, exist_ok=True)

    def ruta_tesseract(self) -> str | None:
        if self.tesseract_cmd and Path(self.tesseract_cmd).exists():
            return self.tesseract_cmd
        encontrado = shutil.which("tesseract")
        if encontrado:
            return encontrado
        for candidato in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                          r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
            if Path(candidato).exists():
                return candidato
        return None
