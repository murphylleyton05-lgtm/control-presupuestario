"""Controles de calidad y conciliación contra las publicaciones oficiales.

Antes de analizar, la suma de las partidas se compara con DOS publicaciones
oficiales de Presupuesto Abierto:

- "Serie anual de gastos, recursos y PIB": devengado anual de los ejercicios cerrados.
- "Total Presupuesto y ejecución": presupuestado, vigente y devengado por ejercicio.

Hallazgo (ver docs/decisiones.md): las dos publicaciones no coinciden entre sí
en 2018-2025. La base detallada coincide al peso con la serie anual en todos los
ejercicios cerrados salvo 2024. Las diferencias se informan, no se esconden.
"""

from __future__ import annotations

import duckdb
import pandas as pd

# Medio millón de pesos: los importes vienen en millones con 6 a 8 decimales y
# la suma de cientos de miles de partidas acumula redondeo.
TOLERANCIA_MILLONES = 0.5


def conciliar(con: duckdb.DuckDBPyConnection, totales: pd.DataFrame, serie: pd.DataFrame) -> pd.DataFrame:
    base = con.execute("""
        SELECT ejercicio,
               sum(presupuestado) AS presupuestado,
               sum(vigente_movimiento) AS vigente,
               sum(devengado) AS devengado
        FROM ejecucion GROUP BY ejercicio
    """).df()
    oficial = totales.rename(columns={
        "credito_presupuestado": "presupuestado_totales",
        "credito_vigente": "vigente_totales",
        "credito_devengado": "devengado_totales",
    })[["ejercicio", "presupuestado_totales", "vigente_totales", "devengado_totales"]]
    df = (base.merge(oficial, on="ejercicio", how="left")
              .merge(serie, on="ejercicio", how="left")
              .sort_values("ejercicio").reset_index(drop=True))

    df["dif_presupuestado"] = df["presupuestado"] - df["presupuestado_totales"]
    df["dif_vigente"] = df["vigente"] - df["vigente_totales"]
    df["dif_devengado_totales"] = df["devengado"] - df["devengado_totales"]
    df["dif_devengado_serie"] = df["devengado"] - df["gasto_serie_anual"]
    df["coincide_totales"] = df[["dif_presupuestado", "dif_vigente", "dif_devengado_totales"]].abs().le(
        TOLERANCIA_MILLONES).all(axis=1)
    # La serie anual solo trae ejercicios cerrados.
    df["coincide_serie_anual"] = df["dif_devengado_serie"].abs().le(TOLERANCIA_MILLONES).where(
        df["gasto_serie_anual"].notna())
    return df


def resumen_conciliacion(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla legible: diferencias en % del devengado de la base."""
    salida = pd.DataFrame({"ejercicio": df["ejercicio"]})
    salida["presupuestado_coincide"] = df["dif_presupuestado"].abs().le(TOLERANCIA_MILLONES)
    salida["dif_devengado_vs_serie_%"] = 100 * df["dif_devengado_serie"] / df["devengado"]
    salida["dif_devengado_vs_totales_%"] = 100 * df["dif_devengado_totales"] / df["devengado"]
    salida["dif_vigente_vs_totales_%"] = 100 * df["dif_vigente"] / df["vigente"]
    return salida


def calidad(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Chequeos por ejercicio. Las columnas de problemas deberían dar 0;
    `filas_devengado_negativo` se informa aparte: son reversiones contables
    legítimas, pero conviene saber cuántas hay."""
    return con.execute("""
        SELECT ejercicio,
               count(*) AS filas,
               count(*) FILTER (WHERE mes NOT BETWEEN 1 AND 12) AS meses_invalidos,
               count(*) FILTER (WHERE jurisdiccion_id IS NULL OR inciso_id IS NULL) AS claves_nulas,
               count(*) FILTER (WHERE presupuestado <> 0 AND mes <> 1) AS presupuestado_fuera_de_enero,
               count(*) FILTER (WHERE devengado < 0) AS filas_devengado_negativo
        FROM ejecucion GROUP BY ejercicio ORDER BY ejercicio
    """).df()


def problemas_de_calidad(df_calidad: pd.DataFrame) -> int:
    return int(df_calidad[["meses_invalidos", "claves_nulas", "presupuestado_fuera_de_enero"]].sum().sum())
