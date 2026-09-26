"""Núcleo del modo asistido por IA (Claude Desktop / ChatGPT Desktop vía MCP).

El modelo del chat interpreta la página (qué texto va con qué oferta). Este módulo:
  1. prepara cada página: imagen + capa de texto + lista de precios detectados en el PDF,
  2. verifica lo que devuelve el modelo contra el texto real del PDF:
     - cada importe devuelto debe existir en la página (evita datos inventados o mal leídos),
     - cada precio de la página debe acabar en una oferta o descartarse con motivo (exhaustividad),
  3. guarda el progreso por página en una sesión JSON, para poder continuar en otro chat.
"""
from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pdfplumber
import pymupdf
from pydantic import BaseModel, Field

from . import lectura
from .config import Config
from .lineas import construir_lineas
from .modelos import Linea, Precio
from .precios import clasificar_por_tamano, detectar_precios, marcar_tachados, mismo_precio, solapa_con_alguno

# Textos legales o de condiciones cuyos importes no son ofertas
_LEGAL = re.compile(r"importe|m[aá]ximo|m[ií]nimo de compra|financ|cuota|\bt\.?a\.?e\b|\bt\.?i\.?n\b|comisi[oó]n|intereses|"
                    r"bases|sorteo|premio|concurso|legislaci|reembols|plazo|gastos|coste total|adeudado", re.IGNORECASE)

CAMPOS_IMPORTE = ["precio_oferta", "precio_normal", "precio_total_lote", "precio_segunda_unidad", "cupon_euros",
                  "precio_unitario", "precio_unitario_normal"]


# --- Esquema que rellena el modelo --------------------------------------------------------

class OfertaEntrada(BaseModel):
    producto: str = Field(description="Descripción del producto tal como aparece (o la categoría si es 'En TODOS los...')")
    marca: str | None = None
    formato: str | None = Field(None, description="Envase y cantidad: 'Lata 50 cl', 'Pack 6 x 1 l', '200 g'")
    seccion: str | None = None
    precio_oferta: float | None = Field(None, description="Precio destacado (el grande). null si solo hay sello de promoción")
    nota_precio_oferta: str | None = Field(None, description="Qué significa el precio destacado: 'Comprando 3, la unidad sale a', 'La 2ª unidad sale a', 'La unidad'...")
    precio_normal: float | None = Field(None, description="Precio sin promoción: tachado, 'antes' o '1 unidad X€'")
    precio_total_lote: float | None = Field(None, description="Precio del lote, p. ej. '3 unidades 9,78€'")
    unidades_lote: int | None = None
    precio_segunda_unidad: float | None = None
    cupon_euros: float | None = Field(None, description="Importe del cupón para la próxima compra")
    descuento_pct: float | None = Field(None, description="Porcentaje anunciado sin signo (30 para -30%)")
    promocion: str | None = Field(None, description="'3x2', '2x1', '2ª unidad -50%', '-30% en cupón'...")
    precio_unitario: float | None = Field(None, description="Precio por kg/l con la promoción")
    unidad_precio_unitario: str | None = Field(None, description="'€/kg', '€/l', '€/ud'...")
    precio_unitario_normal: float | None = Field(None, description="Precio por kg/l sin promoción")
    condiciones: str | None = Field(None, description="Tarjeta Club, máximo de unidades, solo hipermercados...")
    vigencia: str | None = Field(None, description="Fechas propias de la oferta si difieren del folleto")


class PrecioDescartado(BaseModel):
    id: str = Field(description="Identificador del precio detectado, p. ej. 'P7'")
    motivo: str = Field(description="Por qué no es una oferta: 'límite de cupón', 'texto legal', 'duplicado'...")


# --- Análisis de página ------------------------------------------------------------------

@dataclass
class AnalisisPagina:
    numero: int
    lineas: list[Linea]
    precios: list[Precio]   # deduplicados, con id P1..Pn en el orden de la lista
    relevantes: set[int]    # índices de precios que deben quedar cubiertos
    con_texto: bool
    cobertura_imagen: float
    texto_bruto: str

    def id_precio(self, i: int) -> str:
        return f"P{i + 1}"


class Folleto:
    """Mantiene abierto un PDF y cachea el análisis de sus páginas."""

    def __init__(self, ruta: Path, cfg: Config):
        self.ruta, self.cfg = ruta, cfg
        self.doc = pymupdf.open(ruta)
        self.plumber = pdfplumber.open(ruta) if cfg.triangulacion_pdfplumber else None
        self._cache: dict[int, AnalisisPagina] = {}

    @property
    def paginas(self) -> int:
        return len(self.doc)

    def cerrar(self):
        self.doc.close()
        if self.plumber:
            self.plumber.close()

    def analizar(self, n: int) -> AnalisisPagina:
        if n in self._cache:
            return self._cache[n]
        pag = self.doc[n - 1]
        palabras = lectura.palabras_pymupdf(pag)
        con_texto = len(palabras) >= self.cfg.ocr_umbral_palabras
        lineas = construir_lineas(palabras)
        precios = detectar_precios(lineas, n, self.cfg)
        if self.plumber is not None and con_texto:
            for q in detectar_precios(construir_lineas(lectura.palabras_pdfplumber(self.plumber.pages[n - 1])),
                                      n, self.cfg, motor="pdfplumber"):
                if q.con_euro and not any(mismo_precio(p, q) for p in precios) and not solapa_con_alguno(q, precios):
                    precios.append(q)
        # Texto con contorno o sombra: el mismo precio dos veces en el mismo sitio
        unicos: list[Precio] = []
        for p in precios:
            if not any(mismo_precio(p, u, tolerancia=3) for u in unicos):
                unicos.append(p)
        marcar_tachados(unicos, lectura.trazos_tachado(pag))
        clasificar_por_tamano(unicos, self.cfg)
        unicos.sort(key=lambda p: (round(p.y0 / 5), p.x0))

        mediana = statistics.median([w.tamano for w in palabras]) if palabras else 10
        relevantes = {i for i, p in enumerate(unicos)
                      if p.tipo != "condicion" and not (p.linea and p.tamano <= mediana and _LEGAL.search(p.linea.texto))}
        a = AnalisisPagina(numero=n, lineas=lineas, precios=unicos, relevantes=relevantes, con_texto=con_texto,
                           cobertura_imagen=lectura.cobertura_imagenes(pag),
                           texto_bruto=lectura.normalizar(pag.get_text()))
        self._cache[n] = a
        return a

    def imagen_png(self, n: int, lado_largo: int = 1568) -> bytes:
        pag = self.doc[n - 1]
        escala = lado_largo / max(pag.rect.width, pag.rect.height)
        return pag.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False).tobytes("png")


def texto_para_modelo(a: AnalisisPagina, total: int) -> str:
    partes = [f"PÁGINA {a.numero} de {total}"]
    if not a.con_texto:
        partes.append("Esta página NO tiene capa de texto (es una imagen): extrae las ofertas leyendo la imagen. "
                      "Sus importes no se podrán verificar automáticamente.")
    else:
        partes.append("CAPA DE TEXTO DEL PDF (x, y en puntos desde arriba-izquierda; t = tamaño de letra):")
        partes += [f"[x={l.x0:.0f} y={l.y0:.0f} t={l.tamano:.0f}] {l.texto}" for l in a.lineas]
        partes.append("")
        partes.append("PRECIOS DETECTADOS QUE DEBEN QUEDAR CUBIERTOS (cada uno en una oferta, o en precios_no_oferta con motivo):")
        for i, p in enumerate(a.precios):
            if i in a.relevantes:
                partes.append(f"{a.id_precio(i)} = {p.valor:.2f} € ({p.tipo}{', tachado' if p.tachado else ''}) "
                              f"en «{p.linea.texto if p.linea else ''}»")
        otros = [i for i in range(len(a.precios)) if i not in a.relevantes]
        if otros:
            partes.append("Importes en textos legales/condiciones (no hace falta cubrirlos): "
                          + ", ".join(f"{a.id_precio(i)}={a.precios[i].valor:.2f}" for i in otros))
    return "\n".join(partes)


# --- Verificación ------------------------------------------------------------------------

def verificar(a: AnalisisPagina, ofertas: list[OfertaEntrada], descartes: list[PrecioDescartado]) -> dict:
    """Empareja los importes del modelo con los precios del PDF y devuelve el informe."""
    por_valor: dict[float, list[int]] = {}
    for i, p in enumerate(a.precios):
        por_valor.setdefault(round(p.valor, 2), []).append(i)
    ids_descartados = {d.id.strip().upper() for d in descartes}
    descartados = {i for i in range(len(a.precios)) if a.id_precio(i) in ids_descartados}
    usados: set[int] = set()
    no_encontrados, anclas, cubiertos_por = [], [], {}
    for k, o in enumerate(ofertas):
        ancla = None
        for campo in CAMPOS_IMPORTE:
            v = getattr(o, campo)
            if v is None:
                continue
            v = round(float(v), 2)
            candidatos = por_valor.get(v, [])
            libres = [i for i in candidatos if i not in usados]
            # primero los precios no descartados, luego cualquiera con ese importe
            preferidos = [i for i in libres if i not in descartados]
            elegido = (preferidos or libres or candidatos or [None])[0]
            if elegido is None:
                if a.con_texto:
                    no_encontrados.append({"oferta": k + 1, "producto": o.producto, "campo": campo, "valor": v})
                continue
            usados.add(elegido)
            cubiertos_por.setdefault(elegido, k + 1)
            if ancla is None:  # precio_oferta va primero en CAMPOS_IMPORTE
                ancla = elegido
        anclas.append(ancla)

    sin_cubrir = [i for i in sorted(a.relevantes)
                  if i not in usados and a.id_precio(i) not in ids_descartados]
    sin_descripcion = [k + 1 for k, o in enumerate(ofertas) if not (o.producto or "").strip()]
    if not a.con_texto:
        estado = "SIN VERIFICAR (página imagen)"
    elif sin_cubrir or no_encontrados or sin_descripcion:
        estado = "CON AVISOS"
    else:
        estado = "VERIFICADA"
    return {
        "estado": estado,
        "anclas": anclas,
        "cubiertos_por": {a.id_precio(i): k for i, k in cubiertos_por.items()},
        "no_encontrados": no_encontrados,
        "sin_cubrir": [{"id": a.id_precio(i), "valor": a.precios[i].valor, "tipo": a.precios[i].tipo,
                        "linea": a.precios[i].linea.texto if a.precios[i].linea else ""} for i in sin_cubrir],
        "sin_descripcion": sin_descripcion,
    }


def informe_texto(n: int, v: dict, total_ofertas: int) -> str:
    lineas = [f"Página {n}: {total_ofertas} oferta(s) guardadas. Estado: {v['estado']}."]
    if v["no_encontrados"]:
        lineas.append("Importes que NO aparecen en el texto del PDF (revisa si están mal leídos o calculados):")
        lineas += [f"  - oferta {x['oferta']} «{x['producto']}»: {x['campo']} = {x['valor']:.2f}" for x in v["no_encontrados"]]
    if v["sin_cubrir"]:
        lineas.append("Precios del PDF que no están en ninguna oferta (añade la oferta que falta o "
                      "indícalos en precios_no_oferta con su motivo):")
        lineas += [f"  - {x['id']} = {x['valor']:.2f} € ({x['tipo']}) en «{x['linea']}»" for x in v["sin_cubrir"]]
    if v["sin_descripcion"]:
        lineas.append(f"Ofertas sin producto: {v['sin_descripcion']}")
    if v["estado"] == "CON AVISOS":
        lineas.append("Corrige y vuelve a llamar a guardar_pagina con la lista COMPLETA de ofertas de la página "
                      "(sustituye a la anterior).")
    return "\n".join(lineas)


# --- Sesión persistente ------------------------------------------------------------------

class Sesion:
    """Un archivo JSON por página: varios procesos pueden guardar páginas a la vez sin pisarse."""

    def __init__(self, ruta_pdf: Path, cfg: Config, paginas: int):
        self.ruta_pdf = ruta_pdf
        self.carpeta = cfg.carpeta_salida / ".sesiones" / ruta_pdf.stem
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.paginas_total = paginas

    @property
    def datos(self) -> dict:
        paginas = {}
        for f in self.carpeta.glob("pagina_*.json"):
            paginas[str(int(f.stem.split("_")[1]))] = json.loads(f.read_text(encoding="utf-8"))
        return {"archivo": self.ruta_pdf.name, "paginas_total": self.paginas_total, "paginas": paginas}

    def guardar_pagina(self, n: int, ofertas: list[OfertaEntrada], descartes: list[PrecioDescartado],
                       vigencia: str | None, verificacion: dict, a: AnalisisPagina) -> None:
        anclas = []
        for i in verificacion["anclas"]:
            if i is None:
                anclas.append(None)
            else:
                p = a.precios[i]
                anclas.append({"id": a.id_precio(i), "x": round(p.x0, 1), "y": round(p.y0, 1),
                               "linea": p.linea.texto if p.linea else ""})
        datos = {
            "ofertas": [o.model_dump() for o in ofertas],
            "descartes": [d.model_dump() for d in descartes],
            "vigencia": vigencia,
            "verificacion": {k: v for k, v in verificacion.items() if k != "anclas"},
            "anclas": anclas,
            "guardada": datetime.now().isoformat(timespec="seconds"),
        }
        destino = self.carpeta / f"pagina_{n:03d}.json"
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(destino)  # escritura atómica

    def pendientes(self) -> list[int]:
        hechas = {int(f.stem.split("_")[1]) for f in self.carpeta.glob("pagina_*.json")}
        return [n for n in range(1, self.paginas_total + 1) if n not in hechas]

    def con_avisos(self) -> list[int]:
        return sorted(int(n) for n, p in self.datos["paginas"].items()
                      if p["verificacion"]["estado"] != "VERIFICADA")


# --- Resultado para el Excel -------------------------------------------------------------

def resultado_desde_sesion(sesion: Sesion, folleto: Folleto):
    from collections import Counter

    from .modelos import Caja, Incidencia, Oferta
    from .precios import PATRON_EURO_BRUTO
    from .procesador import _VIGENCIA, Resultado, ResultadoPagina

    res = Resultado(archivo=folleto.ruta, inicio=datetime.now())
    res.ocr_disponible = True  # la lectura de imágenes la hace el modelo del chat
    inc = res.incidencias
    siguiente = 1
    vigencias = []
    paginas_sesion = sesion.datos["paginas"]
    for n in range(1, folleto.paginas + 1):
        a = folleto.analizar(n)
        datos = paginas_sesion.get(str(n))
        bruto = len(PATRON_EURO_BRUTO.findall(a.texto_bruto))
        if datos is None:
            inc.append(Incidencia(n, "ERROR", "Página sin procesar", "El modelo no ha procesado esta página."))
            res.paginas.append(ResultadoPagina(n, "pendiente", len(a.lineas), bruto, 0, len(a.precios), 0, 0, 0,
                                               len(a.relevantes), 0, round(a.cobertura_imagen, 2), "ERROR"))
            continue
        v = datos["verificacion"]
        if datos.get("vigencia"):
            vigencias.append(datos["vigencia"])
        for x in v["no_encontrados"]:
            inc.append(Incidencia(n, "AVISO", "Importe no hallado en PDF",
                                  f"Oferta «{x['producto']}»: {x['campo']} = {x['valor']:.2f} € no aparece en el texto."))
        for x in v["sin_cubrir"]:
            inc.append(Incidencia(n, "AVISO", "Precio sin oferta",
                                  f"{x['id']} = {x['valor']:.2f} € en «{x['linea']}» no está en ninguna oferta."))
        if not a.con_texto:
            inc.append(Incidencia(n, "AVISO", "Página imagen", "Sin capa de texto: importes leídos de la imagen, sin verificar."))
        for d in datos["descartes"]:
            inc.append(Incidencia(n, "INFO", "Precio descartado", f"{d['id']}: {d['motivo']}"))

        ofertas_pag = []
        for k, (o, ancla) in enumerate(zip(datos["ofertas"], datos["anclas"])):
            alertas = []
            nums = {x["oferta"] for x in v["no_encontrados"]}
            if k + 1 in nums:
                alertas.append("Algún importe no aparece en el texto del PDF")
            if o["precio_oferta"] is None:
                alertas.append("Oferta sin precio (solo promoción)")
            if not a.con_texto:
                alertas.append("Página imagen: sin verificar")
            caja = Caja(ancla["x"], ancla["y"], ancla["x"], ancla["y"]) if ancla else Caja(0, 0, 0, 0)
            precio = Precio(valor=o["precio_oferta"], texto="", caja=caja, tamano=0, pagina=n, con_euro=True,
                            tipo="principal" if o["precio_oferta"] is not None else "sello",
                            motor="IA + PDF" if a.con_texto else "IA (imagen)",
                            confianza="alta" if a.con_texto and not alertas else "media")
            descuento = o.get("descuento_pct")
            if descuento is None and o["precio_oferta"] and o["precio_normal"] and o["precio_normal"] > o["precio_oferta"]:
                if o["precio_normal"] <= 3 * o["precio_oferta"]:
                    descuento = round((1 - o["precio_oferta"] / o["precio_normal"]) * 100, 1)
                else:  # p. ej. precio por lata frente al pack tachado entero
                    alertas.append("Precio normal de otro formato (pack): descuento no calculado")
            of = Oferta(id=siguiente, pagina=n, precio=precio, seccion=o.get("seccion") or "", alertas=alertas)
            of.campos = {
                "producto": o["producto"], "marca": o.get("marca"), "formato": o.get("formato"),
                "precio_oferta": o["precio_oferta"], "nota_precio": o.get("nota_precio_oferta"),
                "precio_anterior": o.get("precio_normal"), "descuento_pct": descuento, "promocion": o.get("promocion"),
                "precio_total_lote": o.get("precio_total_lote"),
                "unidades_lote": f"{o['unidades_lote']} uds" if o.get("unidades_lote") else None,
                "precio_segunda_unidad": o.get("precio_segunda_unidad"), "cupon": o.get("cupon_euros"),
                "precio_unitario": o.get("precio_unitario"), "unidad_precio_unitario": o.get("unidad_precio_unitario"),
                "precio_unitario_normal": o.get("precio_unitario_normal"), "condiciones": o.get("condiciones"),
                "vigencia": o.get("vigencia") or datos.get("vigencia"),
                "texto_completo": ancla["linea"] if ancla else "",
            }
            siguiente += 1
            ofertas_pag.append(of)
        res.ofertas.extend(ofertas_pag)

        # Texto bruto: cada línea con la oferta a la que pertenece su precio (si lo tiene)
        linea_oferta = {}
        for pid, k in v["cubiertos_por"].items():
            p = a.precios[int(pid[1:]) - 1]
            if p.linea is not None and k - 1 < len(ofertas_pag):
                linea_oferta[id(p.linea)] = ofertas_pag[k - 1].id
        for l in a.lineas:
            res.lineas_brutas.append((n, l, linea_oferta.get(id(l))))

        estado = {"VERIFICADA": "OK", "CON AVISOS": "REVISAR"}.get(v["estado"], "REVISAR")
        con_precio = sum(1 for o in datos["ofertas"] if o["precio_oferta"] is not None)
        res.paginas.append(ResultadoPagina(n, "IA+verificación" if a.con_texto else "IA (imagen)", len(a.lineas),
                                           bruto, 0, len(a.precios), con_precio, len(a.precios) - con_precio, 0,
                                           len(v["sin_cubrir"]), len(ofertas_pag), round(a.cobertura_imagen, 2), estado))
    texto_doc = " ".join(folleto.analizar(n).texto_bruto for n in range(1, folleto.paginas + 1))
    vig = [m.group(0).strip() for m in _VIGENCIA.finditer(texto_doc)] + vigencias
    res.vigencia = Counter(vig).most_common(1)[0][0] if vig else ""
    return res
