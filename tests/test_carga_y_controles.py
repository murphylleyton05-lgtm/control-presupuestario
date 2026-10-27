from datetime import date

import pandas as pd
import pytest

from presupuesto.carga import fecha_actualizacion, numero_es, zip_a_parquet, conexion
from presupuesto.controles import calidad, conciliar, problemas_de_calidad, resumen_conciliacion

from conftest import escribir_zip, fila


def test_numero_con_coma_decimal():
    assert numero_es("112314,626039") == pytest.approx(112314.626039)
    assert numero_es(" -0,5 ") == -0.5


@pytest.mark.parametrize("texto, esperado", [
    ("Última actualización del ejercicio 2026: 23 Octubre 2026.", date(2026, 10, 23)),
    ("Última actualización del ejercicio 2025: 05 Julio 2026.", date(2026, 7, 5)),
    ("Última actualización del ejercicio 2019: 1 Septiembre 2020.", date(2020, 9, 1)),
    ("sin fecha", None),
    (None, None),
])
def test_fecha_de_actualizacion(texto, esperado):
    assert fecha_actualizacion(texto) == esperado


def test_zip_a_parquet_suma_partidas_y_tolera_vacios(tmp_path):
    filas = [fila(2025, 1, presupuestado=10.5, vigente=10.5, devengado=1.25),
             fila(2025, 1, presupuestado=4.5, vigente=4.5, devengado=0.75),  # misma combinación de claves
             fila(2025, 2, devengado=2.0)]
    filas[2][-3] = ""  # devengado vacío en el archivo -> 0
    escribir_zip(tmp_path / "x.zip", 2025, filas)
    n = zip_a_parquet(tmp_path / "x.zip", tmp_path / "p" / "ejecucion_2025.parquet", tmp_path / "tmp")
    assert n == 2
    df = conexion(tmp_path / "p").execute(
        "SELECT mes, presupuestado, devengado FROM ejecucion ORDER BY mes").df()
    assert df.presupuestado.tolist() == [15.0, 0.0]
    assert df.devengado.tolist() == [2.0, 0.0]
    assert not list((tmp_path / "tmp").glob("*.csv"))  # el CSV temporal se borra


def test_conciliacion(base):
    totales = pd.DataFrame({"ejercicio": [2025, 2026], "credito_presupuestado": [5200.0, 10400.0],
                            "credito_vigente": [5600.0, 10400.0], "credito_devengado": [5200.0, 8000.0]})
    serie = pd.DataFrame({"ejercicio": [2025], "gasto_serie_anual": [5200.0 + 10]})  # difiere en 10 millones
    df = conciliar(base, totales, serie).set_index("ejercicio")
    assert df.loc[2025, "coincide_totales"] and df.loc[2026, "coincide_totales"]
    assert df.loc[2025, "coincide_serie_anual"] == False  # noqa: E712
    assert pd.isna(df.loc[2026, "coincide_serie_anual"])  # la serie no trae el año en curso
    assert df.loc[2023, "coincide_totales"] == False  # noqa: E712  (sin dato oficial)
    resumen = resumen_conciliacion(df.reset_index()).set_index("ejercicio")
    assert resumen.loc[2025, "dif_devengado_vs_serie_%"] == pytest.approx(-100 * 10 / 5200)


def test_calidad_sin_problemas(base):
    assert problemas_de_calidad(calidad(base)) == 0
