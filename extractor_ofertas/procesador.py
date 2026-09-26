"""Pipeline completo: lectura híbrida -> precios -> agrupación -> interpretación -> auditoría."""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pdfplumber
import pymupdf

from . import lectura
from .agrupacion import agrupar
from .config import Config
from .interpretacion import interpretar
from .lineas import construir_lineas
from .modelos import Incidencia, Linea, Oferta, Precio
from .precios import (PATRON_EURO_BRUTO, clasificar_por_tamano, detectar_precios, marcar_tachados,
                      mismo_precio, solapa_con_alguno)

log = logging.getLogger(__name__)

_VIGENCIA = re.compile(
    r"(?:del?\s+\d{1,2}(?:\s*(?:de\s+)?[a-záéíóú]+|[./-]\d{1,2}(?:[./-]\d{2,4})?)?\s+al?\s+\d{1,2}"
    r"(?:\s*(?:de\s+)?[a-záéíóú]+|[./-]\d{1,2}(?:[./-]\d{2,4})?)(?:\s+(?:de\s+)?\d{4})?|"
    r"(?:v[aá]lid[oa]s?|oferta[s]?)\s+hasta\s+(?:el\s+)?\d{1,2}(?:\s*(?:de\s+)?[a-záéíóú]+|[./-]\d{1,2}(?:[./-]\d{2,4})?))",
    re.IGNORECASE)


@dataclass
class ResultadoPagina:
    numero: int
    metodo: str
    palabras: int
    bruto_pymupdf: int
    bruto_pdfplumber: int
    precios_detectados: int
    precios_principales: int
    precios_secundarios: int
    recuperados_triangulacion: int
    huerfanos: int
    ofertas: int
    cobertura_imagen: float
    estado: str = "OK"


@dataclass
class Resultado:
    archivo: Path
    inicio: datetime
    ofertas: list[Oferta] = field(default_factory=list)
    paginas: list[ResultadoPagina] = field(default_factory=list)
    incidencias: list[Incidencia] = field(default_factory=list)
    lineas_brutas: list[tuple[int, Linea, int | None]] = field(default_factory=list)
    huerfanos: list[Precio] = field(default_factory=list)
    vigencia: str = ""
    ocr_disponible: bool = False

    @property
    def estado(self) -> str:
        if any(i.gravedad == "ERROR" for i in self.incidencias):
            return "REVISAR (errores)"
        if any(i.gravedad == "AVISO" for i in self.incidencias):
            return "COMPLETO CON AVISOS"
        return "COMPLETO Y VERIFICADO"


def procesar_pdf(ruta: Path, cfg: Config) -> Resultado:
    res = Resultado(archivo=ruta, inicio=datetime.now())
    res.ocr_disponible = lectura.ocr_disponible(cfg)
    if not res.ocr_disponible:
        res.incidencias.append(Incidencia(None, "INFO", "OCR no disponible",
                                          "Tesseract no está instalado; las páginas escaneadas no se podrán leer."))
    doc = pymupdf.open(ruta)
    plumber = pdfplumber.open(ruta) if cfg.triangulacion_pdfplumber else None
    texto_doc = []
    siguiente_id = 1
    try:
        for i, pag in enumerate(doc):
            n = i + 1
            log.info("  página %d/%d", n, len(doc))
            rp, ofertas = _procesar_pagina(pag, plumber.pages[i] if plumber else None, n, cfg, res, siguiente_id)
            siguiente_id += len(ofertas)
            res.ofertas.extend(ofertas)
            res.paginas.append(rp)
            texto_doc.append(lectura.normalizar(pag.get_text()))
    finally:
        doc.close()
        if plumber:
            plumber.close()

    vig = [m.group(0).strip() for m in _VIGENCIA.finditer("\n".join(texto_doc))]
    res.vigencia = Counter(vig).most_common(1)[0][0] if vig else ""
    if not res.ofertas:
        res.incidencias.append(Incidencia(None, "ERROR", "Sin ofertas", "No se ha detectado ninguna oferta en el PDF."))
    return res


def _procesar_pagina(pag, pag_plumber, n: int, cfg: Config, res: Resultado, siguiente_id: int):
    inc = res.incidencias
    palabras = lectura.palabras_pymupdf(pag)
    metodo = "texto"
    cobertura = lectura.cobertura_imagenes(pag)
    texto_bruto = lectura.normalizar(pag.get_text())
    bruto_fitz = len(PATRON_EURO_BRUTO.findall(texto_bruto))

    texto_plumber, palabras_pl = "", []
    if pag_plumber is not None:
        try:
            texto_plumber = lectura.normalizar(pag_plumber.extract_text() or "")
        except Exception as e:
            inc.append(Incidencia(n, "INFO", "pdfplumber", f"No pudo leer la página: {e}"))
        palabras_pl = lectura.palabras_pdfplumber(pag_plumber)
    bruto_pl = len(PATRON_EURO_BRUTO.findall(texto_plumber))

    # --- Capa OCR de respaldo ---
    necesita_ocr = len(palabras) < cfg.ocr_umbral_palabras
    if necesita_ocr:
        if res.ocr_disponible:
            palabras = lectura.palabras_ocr(pag, cfg)
            metodo = "OCR"
            inc.append(Incidencia(n, "INFO", "OCR", "Página sin capa de texto: leída con OCR. Revisar precios."))
        else:
            inc.append(Incidencia(n, "ERROR", "Página sin texto",
                                  "La página es una imagen y no hay OCR instalado: sus ofertas NO se han extraído."))

    lineas = construir_lineas(palabras)
    precios = detectar_precios(lineas, n, cfg, motor="pymupdf" if metodo == "texto" else "ocr")

    # --- Triangulación con pdfplumber ---
    recuperados = 0
    if metodo == "texto" and palabras_pl:
        lineas_pl = construir_lineas(palabras_pl)
        for q in detectar_precios(lineas_pl, n, cfg, motor="pdfplumber"):
            if q.con_euro and not any(mismo_precio(p, q) for p in precios) and not solapa_con_alguno(q, precios):
                precios.append(q)
                lineas.append(q.linea)
                recuperados += 1
        if recuperados:
            inc.append(Incidencia(n, "AVISO", "Triangulación",
                                  f"pdfplumber encontró {recuperados} precio(s) que PyMuPDF no vio; se han añadido."))
    elif metodo == "OCR" and cobertura > 0.5 and not precios:
        inc.append(Incidencia(n, "AVISO", "OCR sin precios", "El OCR no encontró precios en una página de imagen."))

    if metodo == "texto" and cobertura > 0.6 and not precios:
        inc.append(Incidencia(n, "AVISO", "Página de imagen",
                              f"La página es {cobertura:.0%} imagen y no tiene precios en texto; "
                              "puede contener ofertas rasterizadas."))

    marcar_tachados(precios, lectura.trazos_tachado(pag))
    clasificar_por_tamano(precios, cfg)
    ofertas, sin_asignar, huerfanos, cabeceras, condiciones = agrupar(
        lineas, precios, n, cfg, siguiente_id, lectura.contenedores(pag), excluir=(_VIGENCIA,),
        alto_pagina=pag.rect.height)
    for of in ofertas:
        interpretar(of)
    # Un sello de promoción sin ningún texto de producto alrededor es decoración de la página
    descartados = [o for o in ofertas if o.precio.tipo == "sello" and not o.campos.get("producto")]
    ofertas = [o for o in ofertas if o not in descartados]
    for i, of in enumerate(ofertas):
        of.id = siguiente_id + i
    if condiciones:
        inc.append(Incidencia(n, "INFO", "Importes en condiciones",
                              f"{len(condiciones)} importe(s) en textos legales/condiciones, no son ofertas: "
                              + ", ".join(p.texto for p in condiciones[:8]) + ("..." if len(condiciones) > 8 else "")))

    # --- Auditoría de la página ---
    detectados_euro = [p for p in precios if p.con_euro]
    valores_bruto = Counter(_valores(texto_bruto))
    valores_det = Counter(round(p.valor, 2) for p in detectados_euro)
    faltan = valores_bruto - valores_det
    # Céntimos en superíndice: el texto bruto ve "99 €" donde nosotros vemos "1,99 €"
    centimos = {round(p.valor * 100) % 100 for p in precios}
    faltan = Counter({v: c for v, c in faltan.items() if not (v == int(v) and v < 100 and int(v) in centimos)})
    if faltan:
        detalle = ", ".join(f"{v:.2f} €" + (f" (x{c})" if c > 1 else "") for v, c in sorted(faltan.items()))
        inc.append(Incidencia(n, "AVISO", "Conteo de control",
                              f"Precios con € en el texto bruto no reconocidos en ninguna oferta: {detalle}"))
    for p in huerfanos:
        inc.append(Incidencia(n, "AVISO", "Precio huérfano",
                              f"{p.texto} ({p.tipo}) sin oferta cercana. Línea: «{p.linea.texto if p.linea else ''}»"))
    for of in ofertas:
        for a in of.alertas:
            if a.startswith("Precio sin descripción") or a.startswith("Descripción muy larga"):
                inc.append(Incidencia(n, "AVISO", "Calidad de bloque", f"Oferta {of.id} ({of.precio.texto}): {a}"))
    sin_precio = [o for o in ofertas if o.precio.tipo == "sello"]
    if sin_precio:
        inc.append(Incidencia(n, "INFO", "Ofertas sin precio",
                              f"{len(sin_precio)} oferta(s) solo con sello de promoción: "
                              + "; ".join(f"{o.precio.texto} {o.campos.get('producto', '')[:40]}" for o in sin_precio)))

    asignacion = {id(l): of.id for of in ofertas for l in of.lineas}
    for l in lineas:
        res.lineas_brutas.append((n, l, asignacion.get(id(l))))
    res.huerfanos.extend(huerfanos)

    principales = sum(1 for p in precios if p.tipo == "principal")
    rp = ResultadoPagina(numero=n, metodo=metodo, palabras=len(palabras), bruto_pymupdf=bruto_fitz,
                         bruto_pdfplumber=bruto_pl, precios_detectados=len(precios),
                         precios_principales=principales, precios_secundarios=len(precios) - principales,
                         recuperados_triangulacion=recuperados, huerfanos=len(huerfanos), ofertas=len(ofertas),
                         cobertura_imagen=round(cobertura, 2))
    graves = [x for x in inc if x.pagina == n and x.gravedad in ("AVISO", "ERROR")]
    rp.estado = "ERROR" if any(x.gravedad == "ERROR" for x in graves) else ("REVISAR" if graves else "OK")
    return rp, ofertas


def _valores(texto: str) -> list[float]:
    vals = []
    for m in PATRON_EURO_BRUTO.finditer(texto):
        num = re.sub(r"[^\d,.'’]", "", m.group(0))
        num = re.sub(r"[,'’]", ".", num)
        partes = num.split(".")
        try:
            vals.append(round(float("".join(partes[:-1]) + "." + partes[-1]) if len(partes) > 1 else float(num), 2))
        except ValueError:
            pass
    return vals
