"""Tablero web: una página HTML estática con los datos embebidos.

Se publica con GitHub Pages desde `docs/`: cualquiera lo abre con un link, sin
instalar nada. Los datos se calculan acá, con las mismas funciones que el
informe, para cada mes de corte posible del ejercicio en curso. En la página,
el selector de mes cambia todos los indicadores juntos.
"""

from __future__ import annotations

import json
import math
from importlib import resources
from pathlib import Path

import duckdb
import pandas as pd

from . import controles, indicadores, proyeccion

PROGRAMAS_POR_ORGANISMO = 12


def _limpio(valor):
    """NaN e infinitos no existen en JSON: pasan a null."""
    if isinstance(valor, float) and (math.isnan(valor) or math.isinf(valor)):
        return None
    return valor


def _registros(df: pd.DataFrame, columnas: list[str], decimales: int = 2) -> list[dict]:
    return [{c: _limpio(round(v, decimales) if isinstance(v, float) else v) for c, v in fila.items()}
            for fila in df[columnas].to_dict("records")]


def _corte(con, ipc, serie, ejercicio: int, mes: int) -> dict:
    ritmo = indicadores.ritmo_historico(con, mes)
    actual = ritmo[ritmo.ejercicio == ejercicio].iloc[0]
    previos = ritmo[ritmo.ejercicio < ejercicio]
    anterior = ritmo[ritmo.ejercicio == ejercicio - 1].iloc[0]
    total_real = indicadores.variacion_real(con, ipc, None, ejercicio, mes).iloc[0]

    organismos = indicadores.ejecucion_por(con, "jurisdiccion", ejercicio, mes)
    programas = indicadores.ejecucion_por(con, "programa", ejercicio, mes)
    programas["organismo"] = programas.id.str.split("-").str[0]
    columnas_org = ["id", "nombre", "vigente", "devengado", "pct_ejecucion", "pct_ejecucion_anterior",
                    "diferencia_pp", "deuda_flotante", "modificacion_pct"]
    lista_organismos = []
    for org in _registros(organismos, columnas_org):
        propios = programas[programas.organismo == org["id"]].head(PROGRAMAS_POR_ORGANISMO)
        org["programas"] = _registros(propios, ["nombre", "vigente", "devengado", "pct_ejecucion",
                                                "pct_ejecucion_anterior"])
        lista_organismos.append(org)

    def variacion(dimension: str) -> list[dict]:
        tabla = indicadores.variacion_real(con, ipc, dimension, ejercicio, mes)
        # Partidas de menos del 0,5 % del gasto: su variación se dispara por base baja.
        tabla = tabla[tabla.real_anterior >= 0.005 * tabla.real_anterior.sum()]
        return _registros(tabla.sort_values("variacion_real_pct"),
                          ["nombre", "real_anterior", "real_actual", "variacion_real_pct"])

    bt = proyeccion.backtest(serie, mes)
    resumen = proyeccion.resumen_backtest(bt)
    proy = proyeccion.proyeccion_con_rango(serie, ejercicio, mes, resumen.metodo.iloc[0], bt)
    return {
        "kpis": {
            "presupuestado": actual.presupuestado,
            "vigente": actual.vigente_al_corte,
            "devengado": actual.devengado_al_corte,
            "pct_ejecucion": actual.pct_ejecucion_al_corte,
            "pct_min_previo": previos.pct_ejecucion_al_corte.min(),
            "pct_max_previo": previos.pct_ejecucion_al_corte.max(),
            "pct_anterior": anterior.pct_ejecucion_al_corte,
            "modificacion_pct": actual.modificacion_al_corte_pct,
            "variacion_real_pct": total_real.variacion_real_pct,
            "deuda_flotante": actual.devengado_al_corte - actual.pagado_al_corte,
            "deuda_flotante_pct": 100 * (actual.devengado_al_corte - actual.pagado_al_corte) / actual.devengado_al_corte,
            "deuda_flotante_pct_anterior": 100 * (anterior.devengado_al_corte - anterior.pagado_al_corte)
                                           / anterior.devengado_al_corte,
        },
        "organismos": lista_organismos,
        "real_objeto": variacion("inciso"),
        "real_funcion": variacion("funcion"),
        "proyeccion": {
            "metodo": proy["metodo"], "estimado": proy["estimado"], "bajo": proy["bajo"], "alto": proy["alto"],
            "resumen": _registros(resumen, ["metodo", "ejercicios", "error_medio_abs", "error_maximo_abs",
                                            "sesgo_medio"]),
            "puntos": _registros(bt, ["ejercicio", "metodo", "error_pct"]),
        },
    }


def datos(con: duckdb.DuckDBPyConnection, totales: pd.DataFrame, serie_anual: pd.DataFrame,
          ipc: pd.DataFrame, ejercicio: int) -> dict:
    mes_corte, actualizacion = indicadores.mes_de_corte(con, ejercicio)
    mensual = con.execute("SELECT ejercicio, mes, sum(devengado) AS devengado FROM ejecucion GROUP BY 1, 2").df()
    serie = proyeccion.serie_mensual(mensual, ipc)
    curva = indicadores.curva_de_ejecucion(con)
    conciliacion = controles.resumen_conciliacion(controles.conciliar(con, totales, serie_anual))
    return {
        "ejercicio": ejercicio,
        "mes_corte": mes_corte,
        "actualizacion": actualizacion.isoformat() if actualizacion else None,
        "curva": {str(e): [_limpio(round(v, 2)) for v in g.sort_values("mes").pct_acumulado]
                  for e, g in curva.groupby("ejercicio")},
        "cortes": {str(m): _corte(con, ipc, serie, ejercicio, m) for m in range(1, mes_corte + 1)},
        "conciliacion": _registros(conciliacion, list(conciliacion.columns), decimales=3),
    }


def generar(datos_tablero: dict, destino: Path) -> None:
    plantilla = resources.files("presupuesto").joinpath("plantilla_tablero.html").read_text(encoding="utf-8")
    # El JSON va dentro de un <script>: se escapa "<" para que ningún texto pueda cerrar la etiqueta.
    carga = json.dumps(datos_tablero, ensure_ascii=False, default=float).replace("<", "\\u003c")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(plantilla.replace("/*__DATOS__*/null", carga), encoding="utf-8")
