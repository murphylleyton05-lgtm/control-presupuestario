"""Proyección del devengado al cierre del ejercicio, validada con backtesting.

Pregunta de negocio: con lo ejecutado hasta el mes de corte, ¿cuánto se va a
haber gastado al 31 de diciembre? Tres métodos, elegidos por su error sobre
ejercicios pasados (no por intuición):

- lineal: acumulado x 12 / meses. El que usaría cualquiera sin mirar datos.
- estacional_nominal: acumulado / participación media del mismo período en los
  3 ejercicios anteriores. Captura que diciembre siempre pesa más (aguinaldo,
  cierres), pero en años de inflación alta la participación nominal se distorsiona.
- estacional_real: lo mismo con montos deflactados. Lo que falta del año se
  estima en términos reales y se lleva a pesos corrientes suponiendo que la
  inflación mensual de los últimos 3 meses se mantiene. Necesita IPC (desde 2017).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

METODOS = ("lineal", "estacional_nominal", "estacional_real")
AÑOS_PREVIOS = 3


def serie_mensual(devengado_mensual: pd.DataFrame, ipc: pd.DataFrame) -> pd.DataFrame:
    """`devengado_mensual`: ejercicio, mes, devengado. Agrega ipc y devengado real (base arbitraria)."""
    df = devengado_mensual.merge(ipc.rename(columns={"anio": "ejercicio"}), on=["ejercicio", "mes"], how="left")
    df["real"] = df["devengado"] / df["ipc"]
    return df.sort_values(["ejercicio", "mes"]).reset_index(drop=True)


def _participacion(serie: pd.DataFrame, ejercicio: int, mes_corte: int, columna: str) -> float:
    año = serie[serie.ejercicio == ejercicio]
    return año.loc[año.mes <= mes_corte, columna].sum() / año[columna].sum()


def ejercicios_completos(serie: pd.DataFrame) -> list[int]:
    meses = serie.groupby("ejercicio")["mes"].nunique()
    return sorted(meses[meses == 12].index)


def proyectar(serie: pd.DataFrame, ejercicio: int, mes_corte: int, metodo: str) -> float | None:
    """Devengado anual estimado con la información disponible al mes de corte.
    Solo usa ejercicios anteriores a `ejercicio` (nada del futuro)."""
    año = serie[(serie.ejercicio == ejercicio) & (serie.mes <= mes_corte)]
    acumulado = año["devengado"].sum()
    if metodo == "lineal":
        return acumulado * 12 / mes_corte

    columna = "real" if metodo == "estacional_real" else "devengado"
    previos = [a for a in ejercicios_completos(serie) if a < ejercicio
               and serie.loc[serie.ejercicio == a, columna].notna().all()][-AÑOS_PREVIOS:]
    if len(previos) < 2 or (columna == "real" and año["real"].isna().any()):
        return None
    participacion = float(np.mean([_participacion(serie, a, mes_corte, columna) for a in previos]))
    if metodo == "estacional_nominal":
        return acumulado / participacion

    restante_real = año["real"].sum() * (1 / participacion - 1)
    meses_restantes = 12 - mes_corte
    if meses_restantes == 0:
        return acumulado
    ipc = año.set_index("mes")["ipc"]
    inflacion = (ipc[mes_corte] / ipc[max(1, mes_corte - 3)]) ** (1 / min(3, mes_corte - 1)) - 1 if mes_corte > 1 else 0.0
    precio = ipc[mes_corte]
    restante_nominal = sum(restante_real / meses_restantes * precio * (1 + inflacion) ** k
                           for k in range(1, meses_restantes + 1))
    return acumulado + restante_nominal


def backtest(serie: pd.DataFrame, mes_corte: int, desde: int = 2019) -> pd.DataFrame:
    """Para cada ejercicio cerrado desde `desde`: proyección al corte vs. real."""
    filas = []
    for ejercicio in ejercicios_completos(serie):
        if ejercicio < desde:
            continue
        real = serie.loc[serie.ejercicio == ejercicio, "devengado"].sum()
        for metodo in METODOS:
            estimado = proyectar(serie, ejercicio, mes_corte, metodo)
            if estimado is not None:
                filas.append(dict(ejercicio=ejercicio, metodo=metodo, estimado=estimado, real=real,
                                  error_pct=100 * (estimado / real - 1)))
    return pd.DataFrame(filas)


def resumen_backtest(bt: pd.DataFrame) -> pd.DataFrame:
    return (bt.assign(error_abs=bt.error_pct.abs())
              .groupby("metodo")
              .agg(ejercicios=("ejercicio", "count"), error_medio_abs=("error_abs", "mean"),
                   error_maximo_abs=("error_abs", "max"), sesgo_medio=("error_pct", "mean"))
              .sort_values("error_medio_abs").reset_index())


def proyeccion_con_rango(serie: pd.DataFrame, ejercicio: int, mes_corte: int, metodo: str,
                         bt: pd.DataFrame) -> dict:
    """Estimación puntual y rango con los errores mínimo y máximo que el método
    tuvo en el backtest: el rango dice cuánto se equivocó antes, no es un IC formal."""
    estimado = proyectar(serie, ejercicio, mes_corte, metodo)
    errores = bt.loc[bt.metodo == metodo, "error_pct"]
    acumulado = serie.loc[(serie.ejercicio == ejercicio) & (serie.mes <= mes_corte), "devengado"].sum()
    # estimado = real * (1 + e)  =>  real = estimado / (1 + e)
    return dict(metodo=metodo, acumulado_al_corte=acumulado, estimado=estimado,
                bajo=estimado / (1 + errores.max() / 100), alto=estimado / (1 + errores.min() / 100))
