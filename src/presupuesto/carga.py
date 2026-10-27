"""Lectura de los archivos oficiales y conversión a Parquet.

Cómo vienen los datos (verificado contra los totales oficiales, ver controles.py):
- `credito_presupuestado` (presupuesto inicial) aparece solo en el mes 1.
- `credito_vigente` en el mes 1 es el crédito inicial; en los meses siguientes
  trae las MODIFICACIONES del mes. El vigente a un mes es la suma acumulada.
- `credito_comprometido`, `credito_devengado` y `credito_pagado` son flujos del mes.
- Importes en millones de pesos con coma decimal ("112314,626039").

El CSV de cada ejercicio pesa entre 300 y 560 MB; se agrega a las dimensiones
que usa el análisis y queda en Parquet (unas decenas de MB por ejercicio).
"""

from __future__ import annotations

import re
import zipfile
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

DIMENSIONES = [
    "caracter_id", "caracter_desc",
    "jurisdiccion_id", "jurisdiccion_desc",
    "servicio_id", "servicio_desc",
    "programa_id", "programa_desc",
    "finalidad_id", "finalidad_desc",
    "funcion_id", "funcion_desc",
    "inciso_id", "inciso_desc",
    "principal_id", "principal_desc",
    "fuente_financiamiento_id", "fuente_financiamiento_desc",
    "ubicacion_geografica_id", "ubicacion_geografica_desc",
]
IMPORTES = {
    "credito_presupuestado": "presupuestado",
    "credito_vigente": "vigente_movimiento",
    "credito_comprometido": "comprometido",
    "credito_devengado": "devengado",
    "credito_pagado": "pagado",
}

_MESES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"], start=1)}


def _importe(columna: str) -> str:
    # Se lee todo como texto y se convierte acá: así un formato raro en algún
    # ejercicio no cambia el tipo de la columna en silencio.
    return f"coalesce(try_cast(replace(trim({columna}), ',', '.') AS DOUBLE), 0)"


def numero_es(texto: str) -> float:
    """'112314,626039' -> 112314.626039"""
    return float(texto.strip().replace(",", "."))


def fecha_actualizacion(texto: str) -> date | None:
    """'Última actualización del ejercicio 2026: 23 Octubre 2026.' -> date(2026, 10, 23)"""
    encontrado = re.search(r"(\d{1,2})\s+([A-Za-zé]+)\s+(\d{4})", texto or "")
    if not encontrado:
        return None
    dia, mes, anio = encontrado.groups()
    numero_mes = _MESES.get(mes.lower().replace("é", "e"))
    return date(int(anio), numero_mes, int(dia)) if numero_mes else None


def csv_de_zip(ruta_zip: Path, carpeta_tmp: Path) -> Path:
    carpeta_tmp.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta_zip) as z:
        nombre = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        z.extract(nombre, carpeta_tmp)
    return carpeta_tmp / nombre


def zip_a_parquet(ruta_zip: Path, destino: Path, carpeta_tmp: Path) -> int:
    """Convierte un credito-mensual-AAAA.zip a Parquet agregado. Devuelve filas."""
    csv = csv_de_zip(ruta_zip, carpeta_tmp)
    try:
        dims = ", ".join(DIMENSIONES)
        importes = ", ".join(f"sum({_importe(c)}) AS {alias}" for c, alias in IMPORTES.items())
        consulta = f"""
            SELECT CAST(ejercicio_presupuestario AS INTEGER) AS ejercicio,
                   CAST(impacto_presupuestario_mes AS INTEGER) AS mes,
                   {dims}, {importes},
                   max(ultima_actualizacion_fecha) AS actualizacion
            FROM read_csv('{csv.as_posix()}', header = true, all_varchar = true)
            GROUP BY ALL
        """
        destino.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect()
        con.execute(f"COPY ({consulta}) TO '{destino.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
        return con.execute(f"SELECT count(*) FROM read_parquet('{destino.as_posix()}')").fetchone()[0]
    finally:
        csv.unlink(missing_ok=True)


def leer_totales(ruta_zip: Path) -> pd.DataFrame:
    """Totales oficiales por ejercicio (millones de pesos)."""
    with zipfile.ZipFile(ruta_zip) as z:
        nombre = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(nombre) as archivo:
            df = pd.read_csv(archivo, dtype=str, encoding="utf-8-sig")
    for columna in df.columns:
        if columna not in ("ejercicio_presupuestario", "ultima_actualizacion_fecha"):
            df[columna] = df[columna].map(numero_es)
    df["ejercicio_presupuestario"] = df["ejercicio_presupuestario"].astype(int)
    return df.rename(columns={"ejercicio_presupuestario": "ejercicio"})


def leer_serie_anual(ruta: Path) -> pd.DataFrame:
    """Serie anual de gastos de Presupuesto Abierto, en pesos -> millones."""
    df = pd.read_csv(ruta, encoding="utf-8-sig")
    return pd.DataFrame({"ejercicio": df["ejercicio_presupuestario"].astype(int),
                         "gasto_serie_anual": df["gasto"] / 1e6})


def leer_ipc(ruta: Path) -> pd.DataFrame:
    """IPC nacional nivel general, una fila por mes: anio, mes, ipc."""
    df = pd.read_csv(ruta, usecols=["indice_tiempo", "ipc_ng_nacional"], parse_dates=["indice_tiempo"])
    df = df.dropna(subset=["ipc_ng_nacional"])
    return pd.DataFrame({
        "anio": df["indice_tiempo"].dt.year,
        "mes": df["indice_tiempo"].dt.month,
        "ipc": df["ipc_ng_nacional"],
    }).reset_index(drop=True)


def conexion(carpeta_procesado: Path) -> duckdb.DuckDBPyConnection:
    """Conexión con la vista `ejecucion` sobre todos los Parquet procesados."""
    con = duckdb.connect()
    patron = (carpeta_procesado / "ejecucion_*.parquet").as_posix()
    con.execute(f"CREATE VIEW ejecucion AS SELECT * FROM read_parquet('{patron}')")
    return con
