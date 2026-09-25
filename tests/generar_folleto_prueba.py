"""Genera un folleto sintético con maquetaciones típicas para probar el extractor.
Devuelve la lista de ofertas esperadas."""
from __future__ import annotations

from pathlib import Path

import pymupdf

PRODUCTOS = [
    # marca, producto, formato, precio, anterior, pu (valor, unidad), promo
    ("HACENDADO", "Leche semidesnatada", "Pack 6 x 1 l", 5.34, 6.10, (0.89, "l"), ""),
    ("COLA CAO", "Cacao soluble original", "760 g", 4.99, None, (6.57, "kg"), "2ª unidad al 50%"),
    ("", "Plátano de Canarias IGP", "granel", 1.99, 2.49, (1.99, "kg"), ""),
    ("DANONE", "Yogur natural", "4 x 125 g", 1.45, None, None, "3x2"),
    ("", "Pechuga de pollo fileteada", "bandeja 500 g", 3.75, None, (7.50, "kg"), "-20%"),
    ("MAHOU", "Cerveza clásica", "Pack 12 x 33 cl", 8.40, 9.90, (2.12, "l"), ""),
    ("ARIEL", "Detergente líquido", "40 lavados", 12.95, 17.50, None, ""),
    ("", "Aceite de oliva virgen extra", "1 l", 7.49, None, None, "2x1"),
    ("NESCAFÉ", "Café soluble classic", "200 g", 6.25, None, (31.25, "kg"), "Con tu tarjeta Club"),
]


FUENTES = {"ar": "C:/Windows/Fonts/arial.ttf", "arb": "C:/Windows/Fonts/arialbd.ttf"}


def _fuentes(page):
    for nombre, archivo in FUENTES.items():
        page.insert_font(fontname=nombre, fontfile=archivo)


def _precio_grande(page, x, y, valor, tam=34):
    ent, cent = f"{valor:.2f}".split(".")
    page.insert_text((x, y), ent, fontsize=tam, fontname="arb")
    ancho = pymupdf.Font(fontfile=FUENTES["arb"]).text_length(ent, fontsize=tam)
    page.insert_text((x + ancho + 1, y - tam * 0.38), cent, fontsize=tam * 0.45, fontname="arb")
    page.insert_text((x + ancho + 1, y), "€", fontsize=tam * 0.45, fontname="arb")


def generar(ruta: Path) -> list[dict]:
    doc = pymupdf.open()
    esperadas = []
    for num_pag, bloque in enumerate([PRODUCTOS[:6], PRODUCTOS[6:]]):
        page = doc.new_page(width=595, height=842)
        _fuentes(page)
        page.insert_text((40, 50), "OFERTAS DE LA SEMANA", fontsize=24, fontname="arb")
        page.insert_text((40, 72), "Ofertas válidas del 1 al 14 de octubre de 2026", fontsize=9, fontname="ar")
        page.insert_text((40, 110), "ALIMENTACIÓN" if num_pag == 0 else "DROGUERÍA Y DESPENSA",
                         fontsize=16, fontname="arb")
        for k, (marca, prod, fmt, precio, ant, pu, promo) in enumerate(bloque):
            col, fila = k % 3, k // 3
            x, y = 40 + col * 185, 150 + fila * 230
            page.draw_rect(pymupdf.Rect(x - 5, y - 15, x + 170, y + 200), color=(0.8, 0.8, 0.8))
            yy = y
            if marca:
                page.insert_text((x, yy), marca, fontsize=11, fontname="arb")
                yy += 15
            page.insert_text((x, yy), prod, fontsize=9.5, fontname="ar")
            page.insert_text((x, yy + 13), fmt, fontsize=8, fontname="ar")
            if promo:
                page.insert_text((x, yy + 40), promo, fontsize=12, fontname="arb", color=(0.8, 0, 0))
            if ant:
                t = f"{ant:.2f} €".replace(".", ",")
                page.insert_text((x, y + 120), t, fontsize=10, fontname="ar")
                w = pymupdf.Font(fontfile=FUENTES["ar"]).text_length(t, fontsize=10)
                page.draw_line((x, y + 116.5), (x + w, y + 116.5), color=(0, 0, 0), width=1)
            _precio_grande(page, x, y + 160, precio)
            if pu:
                page.insert_text((x, y + 178), f"{pu[0]:.2f} €/{pu[1]}".replace(".", ","), fontsize=7, fontname="ar")
            esperadas.append(dict(pagina=num_pag + 1, marca=marca, producto=prod, precio=precio,
                                  anterior=ant, pu=pu, promo=promo))
    # Página 3: una oferta rasterizada (imagen) -> sin OCR debe generar aviso
    tmp = pymupdf.open()
    p = tmp.new_page(width=300, height=200)
    p.insert_text((20, 60), "Oferta imagen", fontsize=20)
    p.insert_text((20, 130), "9,99 €", fontsize=40)
    pix = p.get_pixmap(dpi=150)
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pix)
    doc.save(ruta)
    return esperadas


if __name__ == "__main__":
    salida = Path(__file__).parent / "folleto_prueba.pdf"
    print(len(generar(salida)), "ofertas ->", salida)
