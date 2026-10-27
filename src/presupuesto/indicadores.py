"""Indicadores de control de gestión sobre la vista `ejecucion`.

Convenciones:
- Fecha de corte: el último mes COMPLETO del ejercicio en curso. Los datos se
  actualizan a diario, así que el mes de la actualización viene parcial y
  compararlo con meses completos de otros años sesgaría todo hacia abajo.
- Vigente al corte = presupuesto inicial + modificaciones hasta el mes de corte.
- Las comparaciones entre años se hacen por CÓDIGO (jurisdicción, función,
  inciso), no por nombre: los nombres cambian entre ejercicios (por ejemplo,
  "Servicio de la Deuda Pública" pasó a "... (intereses y gastos)" en 2026).
  La etiqueta que se muestra es la del ejercicio más reciente.
- Términos reales: pesos del mes de corte, deflactados con el IPC nacional.
"""

from __future__ import annotations

import calendar
from datetime import date

import duckdb
import pandas as pd

from .carga import fecha_actualizacion

DIMENSIONES_COMPARABLES = {
    "jurisdiccion": ("jurisdiccion_id", "jurisdiccion_desc"),
    "funcion": ("finalidad_id || '.' || funcion_id", "funcion_desc"),
    "inciso": ("inciso_id", "inciso_desc"),
    "caracter": ("caracter_id", "caracter_desc"),
}


def mes_de_corte(con: duckdb.DuckDBPyConnection, ejercicio: int) -> tuple[int, date | None]:
    """(último mes completo, fecha de actualización) del ejercicio."""
    texto, ultimo_mes = con.execute(
        "SELECT max(actualizacion), max(mes) FROM ejecucion WHERE ejercicio = ?", [ejercicio]).fetchone()
    actualizada = fecha_actualizacion(texto)
    if actualizada is None or actualizada.year > ejercicio:
        return int(ultimo_mes), actualizada
    ultimo_dia = calendar.monthrange(actualizada.year, actualizada.month)[1]
    completo = actualizada.month if actualizada.day == ultimo_dia else actualizada.month - 1
    return min(int(ultimo_mes), completo), actualizada


def ritmo_historico(con: duckdb.DuckDBPyConnection, mes_corte: int) -> pd.DataFrame:
    """Por ejercicio: cuánto del vigente se había devengado al mes de corte y
    cuánto se modificó el presupuesto hasta ese mes."""
    return con.execute("""
        SELECT ejercicio,
               sum(presupuestado) AS presupuestado,
               sum(vigente_movimiento) FILTER (WHERE mes <= $m) AS vigente_al_corte,
               sum(devengado) FILTER (WHERE mes <= $m) AS devengado_al_corte,
               sum(pagado) FILTER (WHERE mes <= $m) AS pagado_al_corte,
               sum(devengado) AS devengado_anual,
               sum(vigente_movimiento) AS vigente_final
        FROM ejecucion GROUP BY ejercicio ORDER BY ejercicio
    """, {"m": mes_corte}).df().assign(
        pct_ejecucion_al_corte=lambda d: 100 * d.devengado_al_corte / d.vigente_al_corte,
        modificacion_al_corte_pct=lambda d: 100 * (d.vigente_al_corte / d.presupuestado - 1),
    )


def curva_de_ejecucion(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """% del vigente devengado, acumulado mes a mes, para cada ejercicio."""
    df = con.execute("""
        SELECT ejercicio, mes, sum(devengado) AS devengado, sum(vigente_movimiento) AS vigente_mov
        FROM ejecucion GROUP BY ejercicio, mes ORDER BY ejercicio, mes
    """).df()
    agrupado = df.groupby("ejercicio")
    df["pct_acumulado"] = 100 * agrupado["devengado"].cumsum() / agrupado["vigente_mov"].cumsum()
    return df


def _etiquetas(con, expr_id: str, expr_desc: str, ejercicio: int) -> pd.DataFrame:
    return con.execute(f"""
        SELECT CAST({expr_id} AS VARCHAR) AS id, arg_max({expr_desc}, ejercicio) AS nombre
        FROM ejecucion WHERE ejercicio <= ? GROUP BY 1
    """, [ejercicio]).df()


def ejecucion_por(con: duckdb.DuckDBPyConnection, dimension: str, ejercicio: int, mes_corte: int) -> pd.DataFrame:
    """Ejecución al corte por dimensión, contra el mismo corte del año anterior."""
    expr_id, expr_desc = DIMENSIONES_COMPARABLES[dimension]
    df = con.execute(f"""
        SELECT CAST({expr_id} AS VARCHAR) AS id, ejercicio,
               sum(presupuestado) AS presupuestado,
               sum(vigente_movimiento) FILTER (WHERE mes <= $m) AS vigente,
               sum(devengado) FILTER (WHERE mes <= $m) AS devengado,
               sum(pagado) FILTER (WHERE mes <= $m) AS pagado
        FROM ejecucion WHERE ejercicio IN ($e, $e - 1) GROUP BY ALL
    """, {"m": mes_corte, "e": ejercicio}).df()
    actual = df[df.ejercicio == ejercicio].drop(columns="ejercicio")
    anterior = df[df.ejercicio == ejercicio - 1][["id", "vigente", "devengado"]].rename(
        columns={"vigente": "vigente_anterior", "devengado": "devengado_anterior"})
    salida = actual.merge(anterior, on="id", how="left").merge(_etiquetas(con, expr_id, expr_desc, ejercicio), on="id")
    salida["pct_ejecucion"] = 100 * salida.devengado / salida.vigente
    salida["pct_ejecucion_anterior"] = 100 * salida.devengado_anterior / salida.vigente_anterior
    salida["diferencia_pp"] = salida.pct_ejecucion - salida.pct_ejecucion_anterior
    salida["deuda_flotante"] = salida.devengado - salida.pagado
    salida["modificacion_pct"] = 100 * (salida.vigente / salida.presupuestado - 1)
    columnas = ["id", "nombre", "presupuestado", "vigente", "devengado", "pagado", "pct_ejecucion",
                "pct_ejecucion_anterior", "diferencia_pp", "deuda_flotante", "modificacion_pct"]
    return salida[columnas].sort_values("vigente", ascending=False).reset_index(drop=True)


def variacion_real(con: duckdb.DuckDBPyConnection, ipc: pd.DataFrame, dimension: str | None,
                   ejercicio: int, mes_corte: int) -> pd.DataFrame:
    """Devengado enero-corte de este año vs. el anterior, en pesos del mes de corte."""
    con.register("ipc_df", ipc)
    ipc_corte = float(ipc.loc[(ipc.anio == ejercicio) & (ipc.mes == mes_corte), "ipc"].iloc[0])
    expr_id, expr_desc = DIMENSIONES_COMPARABLES[dimension] if dimension else ("'total'", "'Total'")
    df = con.execute(f"""
        SELECT CAST({expr_id} AS VARCHAR) AS id, e.ejercicio,
               sum(e.devengado) AS nominal,
               sum(e.devengado * $ipc_corte / i.ipc) AS real
        FROM ejecucion e JOIN ipc_df i ON i.anio = e.ejercicio AND i.mes = e.mes
        WHERE e.ejercicio IN ($e, $e - 1) AND e.mes <= $m GROUP BY ALL
    """, {"ipc_corte": ipc_corte, "e": ejercicio, "m": mes_corte}).df()
    tabla = df.pivot_table(index="id", columns="ejercicio", values=["nominal", "real"], aggfunc="sum")
    salida = pd.DataFrame({
        "id": tabla.index,
        "nominal_anterior": tabla[("nominal", ejercicio - 1)].values,
        "nominal_actual": tabla[("nominal", ejercicio)].values,
        "real_anterior": tabla[("real", ejercicio - 1)].values,
        "real_actual": tabla[("real", ejercicio)].values,
    })
    salida["variacion_real_pct"] = 100 * (salida.real_actual / salida.real_anterior - 1)
    salida["variacion_real_millones"] = salida.real_actual - salida.real_anterior
    if dimension:
        salida = salida.merge(_etiquetas(con, expr_id, expr_desc, ejercicio), on="id")
    else:
        salida["nombre"] = "Total"
    return salida.sort_values("real_actual", ascending=False).reset_index(drop=True)
