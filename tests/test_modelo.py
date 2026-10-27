import zipfile

import pandas as pd

from presupuesto.modelo import exportar


def test_modelo_estrella(base, ipc_constante, tmp_path):
    ipc = ipc_constante[~((ipc_constante.anio == 2026) & (ipc_constante.mes >= 10))]  # IPC de octubre sin publicar
    filas = exportar(base, ipc, tmp_path / "m", desde=2025, ejercicio_en_curso=2026, mes_corte=9)
    hechos = pd.read_csv(tmp_path / "m" / "hechos_ejecucion.csv")
    assert set(hechos.ejercicio) == {2025, 2026}
    assert hechos.devengado.sum() == 5200 + 8000
    # Cada clave de los hechos existe en su dimensión.
    jurisdicciones = pd.read_csv(tmp_path / "m" / "dim_jurisdiccion.csv")
    assert set(hechos.jurisdiccion_key) <= set(jurisdicciones.clave)

    fechas = pd.read_csv(tmp_path / "m" / "dim_fecha.csv")
    octubre = fechas[(fechas.ejercicio == 2026) & (fechas.mes == 10)].iloc[0]
    assert not octubre.mes_completo and pd.isna(octubre.factor_pesos_constantes)
    assert octubre.mes_nombre == "Oct"
    assert fechas[fechas.ejercicio == 2025].mes_completo.all()

    with zipfile.ZipFile(tmp_path / "m" / "modelo_powerbi.zip") as z:
        assert sorted(z.namelist()) == sorted(f"{t}.csv" for t in filas)
