import pandas as pd
import pytest

from presupuesto import indicadores as ind
from presupuesto import proyeccion as pr
from presupuesto.informe import billones, pct


def test_mes_de_corte_descarta_el_mes_parcial(base):
    assert ind.mes_de_corte(base, 2026)[0] == 9  # actualizado el 23/10: octubre está incompleto
    assert ind.mes_de_corte(base, 2025)[0] == 12  # ejercicio cerrado, actualizado al año siguiente


def test_ritmo_historico(base):
    r = ind.ritmo_historico(base, 9).set_index("ejercicio")
    # 2025: vigente al corte = 5200 + 400 de junio; devengado ene-sep = 9 x 400.
    assert r.loc[2025, "vigente_al_corte"] == pytest.approx(5600)
    assert r.loc[2025, "pct_ejecucion_al_corte"] == pytest.approx(100 * 3600 / 5600)
    assert r.loc[2026, "pct_ejecucion_al_corte"] == pytest.approx(100 * 7200 / 10400)
    assert r.loc[2025, "modificacion_al_corte_pct"] == pytest.approx(100 * 400 / 5200)


def test_variacion_real_deflacta_al_mes_de_corte(base):
    # Precios que se duplican de 2025 a 2026.
    ipc = pd.DataFrame([dict(anio=a, mes=m, ipc=100.0 if a == 2025 else 200.0)
                        for a in (2025, 2026) for m in range(1, 13)])
    t = ind.variacion_real(base, ipc, None, 2026, 9).iloc[0]
    # Ene-sep: 2025 = 9 x 400 = 3600 nominal -> 7200 en pesos de sep-2026; 2026 = 9 x 800 = 7200.
    assert t.real_anterior == pytest.approx(7200) and t.real_actual == pytest.approx(7200)
    assert t.variacion_real_pct == pytest.approx(0)


def test_comparacion_por_codigo_aunque_cambie_el_nombre(tmp_path):
    from conftest import escribir_zip, fila
    from presupuesto.carga import conexion, zip_a_parquet
    for ejercicio, nombre in ((2025, "Ministerio de Hacienda"), (2026, "Ministerio de Economía")):
        escribir_zip(tmp_path / f"{ejercicio}.zip", ejercicio,
                     [fila(ejercicio, 1, jurisdiccion=("50", nombre), presupuestado=100, vigente=100, devengado=50,
                           actualizacion="23 Octubre 2026")])
        zip_a_parquet(tmp_path / f"{ejercicio}.zip", tmp_path / "p" / f"ejecucion_{ejercicio}.parquet", tmp_path / "t")
    t = ind.ejecucion_por(conexion(tmp_path / "p"), "jurisdiccion", 2026, 1)
    assert len(t) == 1
    assert t.nombre.iloc[0] == "Ministerio de Economía" and t.pct_ejecucion_anterior.iloc[0] == pytest.approx(50)


def serie_de(base, ipc):
    mensual = base.execute("SELECT ejercicio, mes, sum(devengado) AS devengado FROM ejecucion GROUP BY 1, 2").df()
    return pr.serie_mensual(mensual, ipc)


def test_metodos_de_proyeccion(base, ipc_constante):
    serie = serie_de(base, ipc_constante)
    # 2025 ene-sep = 3600; participación histórica a septiembre = 900/1300.
    assert pr.proyectar(serie, 2025, 9, "lineal") == pytest.approx(3600 * 12 / 9)
    assert pr.proyectar(serie, 2025, 9, "estacional_nominal") == pytest.approx(3600 * 1300 / 900)
    # Sin inflación, el método real coincide con el nominal.
    assert pr.proyectar(serie, 2025, 9, "estacional_real") == pytest.approx(3600 * 1300 / 900)


def test_backtest_no_usa_el_futuro(base, ipc_constante):
    serie = serie_de(base, ipc_constante)
    antes = pr.proyectar(serie, 2025, 9, "estacional_nominal")
    # Cambiar 2026 (posterior) no puede mover la proyección de 2025.
    alterada = serie.copy()
    alterada.loc[alterada.ejercicio == 2026, "devengado"] *= 10
    assert pr.proyectar(alterada, 2025, 9, "estacional_nominal") == pytest.approx(antes)
    bt = pr.backtest(serie, 9, desde=2025)
    fila_bt = bt[bt.metodo == "estacional_nominal"].iloc[0]
    assert fila_bt.error_pct == pytest.approx(0)  # misma estacionalidad todos los años
    assert set(bt.ejercicio) == {2025}  # 2026 no está cerrado: no entra al backtest


def test_rango_de_la_proyeccion(monkeypatch):
    # En el backtest el método se equivocó entre -5 % y +10 %: el rango invierte esos errores.
    bt = pd.DataFrame({"metodo": ["m", "m"], "error_pct": [-5.0, 10.0]})
    serie = pd.DataFrame({"ejercicio": [2026] * 2, "mes": [1, 2], "devengado": [1.0, 1.0], "ipc": [1, 1], "real": [1, 1]})
    monkeypatch.setattr(pr, "proyectar", lambda *a, **k: 110.0)
    r = pr.proyeccion_con_rango(serie, 2026, 2, "m", bt)
    assert r["bajo"] == pytest.approx(100.0) and r["alto"] == pytest.approx(110 / 0.95)


def test_formatos():
    assert billones(115_851_567.47) == "$ 115,9 billones"
    assert billones(1_234_567_890.0) == "$ 1.234,6 billones"
    assert pct(76.04) == "76,0 %" and pct(-0.3, signo=True) == "-0,3 %"
