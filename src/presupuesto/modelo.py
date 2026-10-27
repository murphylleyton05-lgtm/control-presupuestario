"""Exportación del modelo estrella para Power BI.

Tablas (CSV con punto decimal, UTF-8):
- hechos_ejecucion: una fila por mes y combinación de claves, con los importes.
- dim_fecha: un registro por mes, con el factor para llevar a pesos constantes.
- dim_jurisdiccion, dim_programa, dim_funcion, dim_objeto, dim_fuente, dim_caracter.

Las dimensiones usan la descripción del ejercicio más reciente en que aparece
cada código. Los organismos se reorganizan entre gobiernos: para comparar años
conviene usar funciones u objeto del gasto, que son clasificadores estables.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import duckdb
import pandas as pd

DIMENSIONES = {
    "dim_jurisdiccion": ("CAST(jurisdiccion_id AS VARCHAR)", ["jurisdiccion_desc"]),
    "dim_programa": ("jurisdiccion_id || '-' || servicio_id || '-' || programa_id",
                     ["jurisdiccion_id", "servicio_id", "servicio_desc", "programa_id", "programa_desc"]),
    "dim_funcion": ("finalidad_id || '.' || funcion_id", ["finalidad_desc", "funcion_desc"]),
    "dim_objeto": ("inciso_id || '.' || principal_id", ["inciso_id", "inciso_desc", "principal_desc"]),
    "dim_fuente": ("CAST(fuente_financiamiento_id AS VARCHAR)", ["fuente_financiamiento_desc"]),
    "dim_caracter": ("CAST(caracter_id AS VARCHAR)", ["caracter_desc"]),
}
CLAVES = {
    "jurisdiccion_key": DIMENSIONES["dim_jurisdiccion"][0],
    "programa_key": DIMENSIONES["dim_programa"][0],
    "funcion_key": DIMENSIONES["dim_funcion"][0],
    "objeto_key": DIMENSIONES["dim_objeto"][0],
    "fuente_key": DIMENSIONES["dim_fuente"][0],
    "caracter_key": DIMENSIONES["dim_caracter"][0],
}


def exportar(con: duckdb.DuckDBPyConnection, ipc: pd.DataFrame, destino: Path, desde: int,
             ejercicio_en_curso: int, mes_corte: int) -> dict[str, int]:
    """Escribe las tablas en `destino` y un zip con todas (`modelo_powerbi.zip`)."""
    destino.mkdir(parents=True, exist_ok=True)
    filas = {}
    claves = ", ".join(f"{expr} AS {nombre}" for nombre, expr in CLAVES.items())
    hechos = f"""
        SELECT make_date(ejercicio, mes, 1) AS fecha, ejercicio, mes, {claves},
               sum(presupuestado) AS presupuestado, sum(vigente_movimiento) AS vigente_movimiento,
               sum(comprometido) AS comprometido, sum(devengado) AS devengado, sum(pagado) AS pagado
        FROM ejecucion WHERE ejercicio >= {desde} GROUP BY ALL ORDER BY fecha
    """
    filas["hechos_ejecucion"] = _copiar(con, hechos, destino / "hechos_ejecucion.csv")

    for tabla, (expr_clave, atributos) in DIMENSIONES.items():
        columnas = ", ".join(f"arg_max({a}, ejercicio) AS {a}" for a in atributos)
        consulta = f"""
            SELECT {expr_clave} AS clave, {columnas}
            FROM ejecucion WHERE ejercicio >= {desde} GROUP BY 1 ORDER BY 1
        """
        filas[tabla] = _copiar(con, consulta, destino / f"{tabla}.csv")

    indices = ipc[ipc.anio >= desde].copy()
    indices["fecha"] = pd.to_datetime(dict(year=indices.anio, month=indices.mes, day=1))
    # Multiplicar un importe del mes por este factor lo lleva a pesos del último mes con IPC.
    indices["factor_pesos_constantes"] = indices.ipc.iloc[-1] / indices.ipc
    # Todos los meses con ejecución, tengan o no IPC publicado (el último suele no tenerlo).
    fechas = con.execute(f"SELECT DISTINCT make_date(ejercicio, mes, 1) AS fecha FROM ejecucion "
                         f"WHERE ejercicio >= {desde}").df()
    fechas["fecha"] = pd.to_datetime(fechas.fecha)
    fechas = fechas.merge(indices[["fecha", "ipc", "factor_pesos_constantes"]], on="fecha", how="outer")
    fechas = fechas.sort_values("fecha").reset_index(drop=True)
    fechas.insert(1, "ejercicio", fechas.fecha.dt.year)
    fechas.insert(2, "mes", fechas.fecha.dt.month)
    fechas.insert(3, "mes_nombre", fechas.mes.map(lambda m: ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul",
                                                             "Ago", "Sep", "Oct", "Nov", "Dic"][m - 1]))
    fechas.insert(4, "trimestre", "T" + ((fechas.mes - 1) // 3 + 1).astype(str))
    # El mes en curso viene parcial: el informe filtra por `mes_completo` para comparar con otros años.
    fechas["mes_completo"] = (fechas.ejercicio < ejercicio_en_curso) | (fechas.mes <= mes_corte)
    fechas.to_csv(destino / "dim_fecha.csv", index=False, date_format="%Y-%m-%d")
    filas["dim_fecha"] = len(fechas)

    with zipfile.ZipFile(destino / "modelo_powerbi.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for tabla in filas:
            z.write(destino / f"{tabla}.csv", f"{tabla}.csv")
    return filas


def _copiar(con: duckdb.DuckDBPyConnection, consulta: str, destino: Path) -> int:
    con.execute(f"COPY ({consulta}) TO '{destino.as_posix()}' (HEADER, DELIMITER ',')")
    return con.execute(f"SELECT count(*) FROM read_csv('{destino.as_posix()}')").fetchone()[0]
