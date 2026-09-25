"""Verificación del modo IA (MCP): lo que devuelve el modelo se contrasta con el PDF."""
import pytest

from extractor_ofertas.config import Config
from extractor_ofertas.verificacion import Folleto, OfertaEntrada, PrecioDescartado, verificar

from generar_folleto_prueba import generar


@pytest.fixture(scope="module")
def folleto(tmp_path_factory):
    pdf = tmp_path_factory.mktemp("mcp") / "folleto.pdf"
    esperadas = generar(pdf)
    cfg = Config()
    cfg.ocr_activo = False
    f = Folleto(pdf, cfg)
    yield f, [e for e in esperadas if e["pagina"] == 1]
    f.cerrar()


def _ofertas(esperadas):
    return [OfertaEntrada(producto=e["producto"], marca=e["marca"] or None, precio_oferta=e["precio"],
                          precio_normal=e["anterior"], precio_unitario=e["pu"][0] if e["pu"] else None)
            for e in esperadas]


def test_pagina_completa_verificada(folleto):
    f, esperadas = folleto
    v = verificar(f.analizar(1), _ofertas(esperadas), [])
    assert v["estado"] == "VERIFICADA", v


def test_detecta_oferta_olvidada(folleto):
    f, esperadas = folleto
    v = verificar(f.analizar(1), _ofertas(esperadas[1:]), [])
    assert v["estado"] == "CON AVISOS"
    faltan = {x["valor"] for x in v["sin_cubrir"]}
    assert esperadas[0]["precio"] in faltan and esperadas[0]["anterior"] in faltan


def test_detecta_importe_mal_leido(folleto):
    f, esperadas = folleto
    ofertas = _ofertas(esperadas)
    ofertas[2].precio_oferta = 1.89  # el folleto dice 1,99
    v = verificar(f.analizar(1), ofertas, [])
    assert [x["valor"] for x in v["no_encontrados"]] == [1.89]


def test_descarte_justificado(folleto):
    f, esperadas = folleto
    a = f.analizar(1)
    v = verificar(a, _ofertas(esperadas[1:]), [])
    descartes = [PrecioDescartado(id=x["id"], motivo="prueba") for x in v["sin_cubrir"]]
    assert verificar(a, _ofertas(esperadas[1:]), descartes)["estado"] == "VERIFICADA"


def test_pagina_imagen_sin_verificar(folleto):
    f, _ = folleto
    v = verificar(f.analizar(3), [OfertaEntrada(producto="Oferta imagen", precio_oferta=9.99)], [])
    assert v["estado"].startswith("SIN VERIFICAR")
