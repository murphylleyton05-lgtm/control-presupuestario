import json
import re

import pandas as pd
import pytest

from presupuesto import tablero


def test_datos_y_pagina(base, ipc_constante, tmp_path):
    totales = pd.DataFrame({"ejercicio": [2025, 2026], "credito_presupuestado": [5200.0, 10400.0],
                            "credito_vigente": [5600.0, 10400.0], "credito_devengado": [5200.0, 8000.0]})
    serie = pd.DataFrame({"ejercicio": [2025], "gasto_serie_anual": [5200.0]})
    datos = tablero.datos(base, totales, serie, ipc_constante, 2026)

    # Un corte por cada mes completo: octubre viene parcial y no entra.
    assert datos["mes_corte"] == 9 and list(datos["cortes"]) == [str(m) for m in range(1, 10)]
    kpis = datos["cortes"]["9"]["kpis"]
    assert kpis["pct_ejecucion"] == pytest.approx(100 * 800 * 9 / 10400)
    assert kpis["deuda_flotante"] == pytest.approx(800 + 0.1 * 800 * 8)  # enero no tiene pagos; el resto, el 90 %
    organismo = datos["cortes"]["9"]["organismos"][0]
    assert organismo["nombre"] == "Ministerio de Economía" and organismo["programas"]
    assert len(datos["curva"]["2026"]) == 10

    destino = tmp_path / "docs" / "index.html"
    tablero.generar(datos, destino)
    html = destino.read_text(encoding="utf-8")
    assert "/*__DATOS__*/" not in html
    # Los datos embebidos se leen de vuelta tal cual.
    embebido = re.search(r"const DATOS = (\{.*?\});\n", html, re.S).group(1)
    assert json.loads(embebido)["cortes"]["9"]["kpis"]["pct_ejecucion"] == pytest.approx(kpis["pct_ejecucion"])


def test_ningun_texto_cierra_el_script(tmp_path):
    destino = tmp_path / "index.html"
    tablero.generar({"nombre": "</script><b>"}, destino)
    html = destino.read_text(encoding="utf-8")
    assert html.count("</script>") == 1
