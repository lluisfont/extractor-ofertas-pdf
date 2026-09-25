"""Estructuras de datos compartidas. Coordenadas en puntos PDF, origen arriba-izquierda."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Palabra:
    texto: str
    x0: float
    y0: float
    x1: float
    y1: float
    tamano: float          # tamaño de letra
    negrita: bool = False
    motor: str = "pymupdf"  # pymupdf | pdfplumber | ocr

    @property
    def alto(self) -> float:
        return self.y1 - self.y0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Caja:
    x0: float
    y0: float
    x1: float
    y1: float

    @staticmethod
    def de(elementos) -> "Caja":
        return Caja(min(e.x0 for e in elementos), min(e.y0 for e in elementos),
                    max(e.x1 for e in elementos), max(e.y1 for e in elementos))

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def ancho(self) -> float:
        return self.x1 - self.x0

    @property
    def alto(self) -> float:
        return self.y1 - self.y0


@dataclass
class Linea:
    palabras: list[Palabra]
    texto: str = ""
    # Para cada palabra: (inicio, fin) de su texto dentro de `texto`
    tramos: list[tuple[int, int]] = field(default_factory=list)

    @property
    def caja(self) -> Caja:
        return Caja.de(self.palabras)

    @property
    def tamano(self) -> float:
        return max(p.tamano for p in self.palabras)

    @property
    def x0(self): return min(p.x0 for p in self.palabras)
    @property
    def x1(self): return max(p.x1 for p in self.palabras)
    @property
    def y0(self): return min(p.y0 for p in self.palabras)
    @property
    def y1(self): return max(p.y1 for p in self.palabras)

    def palabras_en(self, ini: int, fin: int) -> list[Palabra]:
        return [p for p, (a, b) in zip(self.palabras, self.tramos) if a < fin and b > ini]


@dataclass
class Precio:
    valor: float
    texto: str
    caja: Caja
    tamano: float
    pagina: int
    con_euro: bool
    tipo: str = "principal"   # principal | unitario | anterior | segunda_unidad | secundario
    unidad: str = ""          # kg, l, ud... para precios unitarios
    tachado: bool = False
    motor: str = "pymupdf"
    linea: Linea | None = None
    confianza: str = "alta"
    oferta_id: int | None = None

    @property
    def x0(self): return self.caja.x0
    @property
    def y0(self): return self.caja.y0
    @property
    def x1(self): return self.caja.x1
    @property
    def y1(self): return self.caja.y1


@dataclass
class Oferta:
    id: int
    pagina: int
    precio: Precio
    lineas: list[Linea] = field(default_factory=list)
    secundarios: list[Precio] = field(default_factory=list)
    seccion: str = ""
    campos: dict = field(default_factory=dict)
    alertas: list[str] = field(default_factory=list)


@dataclass
class Incidencia:
    pagina: int | None
    gravedad: str   # INFO | AVISO | ERROR
    tipo: str
    detalle: str
