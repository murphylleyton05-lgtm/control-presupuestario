"""Datos de prueba chicos con el mismo formato que los archivos oficiales.

Los importes son inventados y redondos para poder verificar las cuentas a mano;
no son datos reales.
"""

import csv
import io
import zipfile

import pandas as pd
import pytest

from presupuesto.carga import DIMENSIONES, conexion, zip_a_parquet

ENCABEZADO = ["impacto_presupuestario_anio", "impacto_presupuestario_mes", "ejercicio_presupuestario",
              *DIMENSIONES, "credito_presupuestado", "credito_vigente", "credito_comprometido",
              "credito_devengado", "credito_pagado", "ultima_actualizacion_fecha"]


def fila(ejercicio, mes, jurisdiccion=("50", "Ministerio de Economía"), inciso=("1", "Gastos en personal"),
         presupuestado=0.0, vigente=0.0, devengado=0.0, pagado=0.0, actualizacion="30 Junio 2026",
         funcion=("3", "1", "SERVICIOS SOCIALES", "Salud")):
    valores = {d: "1" if d.endswith("_id") else "x" for d in DIMENSIONES}
    valores.update(jurisdiccion_id=jurisdiccion[0], jurisdiccion_desc=jurisdiccion[1],
                   inciso_id=inciso[0], inciso_desc=inciso[1],
                   finalidad_id=funcion[0], funcion_id=funcion[1], finalidad_desc=funcion[2], funcion_desc=funcion[3])

    def coma(v):
        return f"{v:.6f}".replace(".", ",")

    return [str(ejercicio), str(mes), str(ejercicio), *[valores[d] for d in DIMENSIONES],
            coma(presupuestado), coma(vigente), coma(devengado), coma(devengado), coma(pagado),
            f"Última actualización del ejercicio {ejercicio}: {actualizacion}."]


def escribir_zip(ruta, ejercicio, filas):
    texto = io.StringIO()
    escritor = csv.writer(texto)
    escritor.writerow(ENCABEZADO)
    escritor.writerows(filas)
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr(f"credito-mensual-{ejercicio}.csv", "﻿" + texto.getvalue())


def año_completo(ejercicio, presupuesto, devengado_por_mes, modificacion_junio=0.0, **kw):
    filas = [fila(ejercicio, 1, presupuestado=presupuesto, vigente=presupuesto, devengado=devengado_por_mes[0], **kw)]
    for mes, dev in enumerate(devengado_por_mes[1:], start=2):
        filas.append(fila(ejercicio, mes, vigente=modificacion_junio if mes == 6 else 0.0, devengado=dev,
                          pagado=dev * 0.9, **kw))
    return filas


@pytest.fixture
def base(tmp_path):
    """2023-2025 completos con la misma estacionalidad (diciembre pesa doble);
    2026 hasta octubre con actualización al 23/10 (septiembre es el último mes completo)."""
    crudo, procesado = tmp_path / "crudo", tmp_path / "procesado"
    crudo.mkdir()
    patron = [100.0] * 11 + [200.0]  # total 1300
    for ejercicio, escala in ((2023, 1.0), (2024, 2.0), (2025, 4.0)):
        escribir_zip(crudo / f"credito-mensual-{ejercicio}.zip", ejercicio,
                     año_completo(ejercicio, 1300 * escala, [v * escala for v in patron],
                                  modificacion_junio=100 * escala, actualizacion=f"30 Junio {ejercicio + 1}"))
    actual = año_completo(2026, 10400.0, [800.0] * 10, actualizacion="23 Octubre 2026")
    escribir_zip(crudo / "credito-mensual-2026.zip", 2026, actual)
    for ejercicio in (2023, 2024, 2025, 2026):
        zip_a_parquet(crudo / f"credito-mensual-{ejercicio}.zip", procesado / f"ejecucion_{ejercicio}.parquet",
                      tmp_path / "tmp")
    return conexion(procesado)


@pytest.fixture
def ipc_constante():
    """IPC sin inflación: real y nominal coinciden."""
    return pd.DataFrame([dict(anio=a, mes=m, ipc=100.0) for a in range(2023, 2027) for m in range(1, 13)])
