"""Informe de control de gestión: tablas, gráficos y un resumen en Markdown.

Todas las cifras del texto salen de las tablas calculadas en la misma corrida;
no hay números escritos a mano.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from . import controles, graficos, indicadores, proyeccion
from .graficos import MESES_LARGOS


def billones(millones: float) -> str:
    """Millones de pesos -> '$ 115,9 billones' (formato argentino)."""
    return "$ " + f"{millones / 1e6:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".") + " billones"


def pct(valor: float, signo: bool = False) -> str:
    texto = f"{valor:+.1f}" if signo else f"{valor:.1f}"
    return texto.replace(".", ",") + " %"


def tabla_md(df: pd.DataFrame) -> str:
    encabezado = "| " + " | ".join(df.columns) + " |"
    separador = "|" + "|".join("---" for _ in df.columns) + "|"
    filas = ["| " + " | ".join(str(v) for v in fila) + " |" for fila in df.itertuples(index=False)]
    return "\n".join([encabezado, separador, *filas])


@dataclass
class Resultados:
    ejercicio: int
    mes_corte: int
    actualizacion: object
    conciliacion: pd.DataFrame
    calidad: pd.DataFrame
    ritmo: pd.DataFrame
    curva: pd.DataFrame
    jurisdicciones: pd.DataFrame
    real_total: pd.DataFrame
    real_inciso: pd.DataFrame
    real_funcion: pd.DataFrame
    backtest: pd.DataFrame
    resumen_backtest: pd.DataFrame
    proyeccion: dict


def calcular(con: duckdb.DuckDBPyConnection, totales: pd.DataFrame, serie_anual: pd.DataFrame,
             ipc: pd.DataFrame, ejercicio: int) -> Resultados:
    mes, actualizacion = indicadores.mes_de_corte(con, ejercicio)
    if not ((ipc.anio == ejercicio) & (ipc.mes == mes)).any():
        raise RuntimeError(f"Todavía no hay IPC publicado para {MESES_LARGOS[mes - 1]} {ejercicio}.")
    mensual = con.execute("SELECT ejercicio, mes, sum(devengado) AS devengado FROM ejecucion GROUP BY 1, 2").df()
    serie = proyeccion.serie_mensual(mensual, ipc)
    bt = proyeccion.backtest(serie, mes)
    resumen_bt = proyeccion.resumen_backtest(bt)
    return Resultados(
        ejercicio=ejercicio, mes_corte=mes, actualizacion=actualizacion,
        conciliacion=controles.conciliar(con, totales, serie_anual),
        calidad=controles.calidad(con),
        ritmo=indicadores.ritmo_historico(con, mes),
        curva=indicadores.curva_de_ejecucion(con),
        jurisdicciones=indicadores.ejecucion_por(con, "jurisdiccion", ejercicio, mes),
        real_total=indicadores.variacion_real(con, ipc, None, ejercicio, mes),
        real_inciso=indicadores.variacion_real(con, ipc, "inciso", ejercicio, mes),
        real_funcion=indicadores.variacion_real(con, ipc, "funcion", ejercicio, mes),
        backtest=bt, resumen_backtest=resumen_bt,
        proyeccion=proyeccion.proyeccion_con_rango(serie, ejercicio, mes, resumen_bt.metodo.iloc[0], bt),
    )


def guardar_tablas(r: Resultados, carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    r.conciliacion.to_csv(carpeta / "conciliacion.csv", index=False)
    r.calidad.to_csv(carpeta / "calidad.csv", index=False)
    r.ritmo.to_csv(carpeta / "ritmo_historico.csv", index=False)
    r.jurisdicciones.to_csv(carpeta / "ejecucion_por_jurisdiccion.csv", index=False)
    pd.concat([r.real_total.assign(apertura="total"), r.real_inciso.assign(apertura="objeto del gasto"),
               r.real_funcion.assign(apertura="función")]).to_csv(carpeta / "variacion_real.csv", index=False)
    r.backtest.to_csv(carpeta / "backtest_proyeccion.csv", index=False)
    pd.DataFrame([r.proyeccion]).to_csv(carpeta / "proyeccion_cierre.csv", index=False)


def generar_graficos(r: Resultados, carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    mes = MESES_LARGOS[r.mes_corte - 1]
    graficos.curva_de_ejecucion(r.curva, r.ejercicio, r.mes_corte, carpeta / "curva_ejecucion.png")
    graficos.ejecucion_por_jurisdiccion(r.jurisdicciones, r.ejercicio, r.mes_corte, carpeta / "ejecucion_jurisdicciones.png")
    graficos.variacion_real(r.real_inciso, "Qué se gasta: variación real por objeto del gasto",
                            f"Devengado enero-{mes} {r.ejercicio} vs. {r.ejercicio - 1}, en pesos de {mes} {r.ejercicio}"
                            " · partidas con al menos 0,5 % del gasto",
                            carpeta / "variacion_real_objeto.png")
    graficos.variacion_real(r.real_funcion, "Para qué se gasta: variación real por función",
                            f"Devengado enero-{mes} {r.ejercicio} vs. {r.ejercicio - 1}, en pesos de {mes} {r.ejercicio}"
                            " · funciones con al menos 0,5 % del gasto", carpeta / "variacion_real_funcion.png")
    graficos.backtest(r.backtest, r.mes_corte, carpeta / "backtest_proyeccion.png")


def _ritmo_tabla(r: Resultados) -> pd.DataFrame:
    df = r.ritmo
    return pd.DataFrame({
        "Ejercicio": df.ejercicio,
        f"% del vigente devengado a fin de {MESES_LARGOS[r.mes_corte - 1]}": df.pct_ejecucion_al_corte.map(pct),
        "Modificación del presupuesto al corte": df.modificacion_al_corte_pct.map(lambda v: pct(v, True)),
    })


def _conciliacion_tabla(conciliacion: pd.DataFrame) -> pd.DataFrame:
    df = controles.resumen_conciliacion(conciliacion)

    def diferencia(v: float) -> str:
        if pd.isna(v):
            return "-"
        if abs(v) < 0.0005:
            return "0"
        if abs(v) < 0.005:
            return "< 0,01 %"
        return (f"{v:+.2f}" if abs(v) < 0.1 else f"{v:+.1f}").replace(".", ",") + " %"

    return pd.DataFrame({
        "Ejercicio": df.ejercicio,
        "Presupuesto inicial": df.presupuestado_coincide.map({True: "coincide", False: "difiere"}),
        "Devengado vs. serie anual": df["dif_devengado_vs_serie_%"].map(diferencia),
        "Devengado vs. totales": df["dif_devengado_vs_totales_%"].map(diferencia),
        "Vigente vs. totales": df["dif_vigente_vs_totales_%"].map(diferencia),
    })


def _lectura_proyeccion(p: dict, vigente: float) -> str:
    if p["bajo"] > vigente:
        return ("Aun el extremo bajo del rango supera el crédito vigente: con este ritmo, el presupuesto actual "
                "no alcanza sin nuevas ampliaciones o una desaceleración del gasto.")
    if p["estimado"] > vigente:
        return "La estimación central supera el crédito vigente, aunque el rango incluye escenarios por debajo."
    return "La estimación cabe dentro del crédito vigente."


def markdown(r: Resultados) -> str:
    e, m = r.ejercicio, r.mes_corte
    mes = MESES_LARGOS[m - 1]
    actual = r.ritmo[r.ritmo.ejercicio == e].iloc[0]
    previos = r.ritmo[r.ritmo.ejercicio < e]
    anterior = r.ritmo[r.ritmo.ejercicio == e - 1].iloc[0]
    rango_previo = f"entre {pct(previos.pct_ejecucion_al_corte.min())} y {pct(previos.pct_ejecucion_al_corte.max())}"
    es_maximo = actual.pct_ejecucion_al_corte > previos.pct_ejecucion_al_corte.max()
    total_real = r.real_total.iloc[0]
    deuda_flotante = actual.devengado_al_corte - actual.pagado_al_corte
    deuda_flotante_ant = anterior.devengado_al_corte - anterior.pagado_al_corte
    p = r.proyeccion
    # Cuánto creció el vigente entre el corte y diciembre en los años cerrados.
    crecimiento_vigente = 100 * (previos.vigente_final / previos.vigente_al_corte - 1)
    ok_serie = r.conciliacion.coincide_serie_anual.dropna()
    sin_conciliar = r.conciliacion.loc[r.conciliacion.coincide_serie_anual == False, "ejercicio"].tolist()  # noqa: E712
    inc = r.real_inciso.set_index("nombre")
    mejor = r.resumen_backtest.iloc[0]

    lineas = [
        f"# Control presupuestario de la Administración Pública Nacional · enero-{mes} {e}",
        "",
        f"Datos de Presupuesto Abierto actualizados al {r.actualizacion:%d/%m/%Y}. Se analiza hasta el último mes "
        f"completo ({mes} {e}). Importes en pesos corrientes salvo que se indique \"real\" "
        f"(pesos de {mes} {e}, deflactados con el IPC del INDEC). 1 billón = 1.000.000 de millones.",
        "",
        "## Resumen ejecutivo",
        "",
        f"- **Crédito vigente a fin de {mes}: {billones(actual.vigente_al_corte)}**, "
        f"{pct(actual.modificacion_al_corte_pct, True)} sobre el presupuesto aprobado ({billones(actual.presupuestado)}).",
        f"- **Devengado enero-{mes}: {billones(actual.devengado_al_corte)}, el {pct(actual.pct_ejecucion_al_corte)} del vigente.** "
        + (f"Es el ritmo más alto de la serie {int(previos.ejercicio.min())}-{int(previos.ejercicio.max())} "
           f"(al mismo mes, los años anteriores estuvieron {rango_previo})." if es_maximo else
           f"En {int(previos.ejercicio.min())}-{int(previos.ejercicio.max())} al mismo mes se ejecutó {rango_previo}."),
        f"- **En términos reales, el gasto enero-{mes} quedó {pct(total_real.variacion_real_pct, True)} contra {e - 1}**, "
        f"pero cambió la composición: intereses y deuda {pct(inc.loc[inc.index.str.startswith('Servicio de la deuda'), 'variacion_real_pct'].iloc[0], True)}, "
        f"personal {pct(inc.loc['Gastos en personal', 'variacion_real_pct'], True)}, "
        f"inversión física (bienes de uso) {pct(inc.loc['Bienes de uso', 'variacion_real_pct'], True)}.",
        f"- **Deuda flotante (devengado y todavía no pagado): {billones(deuda_flotante)}**, "
        f"{pct(100 * deuda_flotante / actual.devengado_al_corte)} de lo devengado "
        f"(a {mes} {e - 1}: {pct(100 * deuda_flotante_ant / anterior.devengado_al_corte)}).",
        f"- **Proyección de cierre: {billones(p['estimado'])}** (rango {billones(p['bajo'])} a {billones(p['alto'])}), "
        f"el {pct(100 * p['estimado'] / actual.vigente_al_corte)} del vigente actual. {_lectura_proyeccion(p, actual.vigente_al_corte)} "
        f"En los ejercicios cerrados, el vigente creció entre {mes} y diciembre una mediana de "
        f"{pct(crecimiento_vigente.median())}.",
        "",
        "## 1. Conciliación y calidad de datos",
        "",
        f"Antes de analizar, la base se concilió contra dos publicaciones oficiales. Coincide al peso con la "
        f"\"Serie anual de gastos\" en {int(ok_serie.sum())} de {len(ok_serie)} ejercicios cerrados"
        + (f"; no coincide en {', '.join(map(str, sin_conciliar))}." if sin_conciliar else ".")
        + " El archivo \"Total Presupuesto y ejecución\" difiere de la serie anual en varios ejercicios: las dos "
        "publicaciones oficiales no coinciden entre sí. Detalle en `resultados/tablas/conciliacion.csv`.",
        "",
        tabla_md(_conciliacion_tabla(r.conciliacion)),
        "",
        f"Problemas de calidad (meses inválidos, claves nulas, presupuesto inicial fuera de enero): "
        f"{controles.problemas_de_calidad(r.calidad)}.",
        "",
        "## 2. Ritmo de ejecución",
        "",
        "![Curva de ejecución](graficos/curva_ejecucion.png)",
        "",
        tabla_md(_ritmo_tabla(r)),
        "",
        "## 3. Por organismo",
        "",
        "![Ejecución por organismo](graficos/ejecucion_jurisdicciones.png)",
        "",
        "Los organismos se reorganizan entre gestiones: se comparan por código y solo cuando el código existe "
        "los dos años. Tabla completa en `resultados/tablas/ejecucion_por_jurisdiccion.csv`.",
        "",
        "## 4. Qué y para qué se gasta, en términos reales",
        "",
        "![Variación real por objeto](graficos/variacion_real_objeto.png)",
        "",
        "![Variación real por función](graficos/variacion_real_funcion.png)",
        "",
        "## 5. Proyección de cierre",
        "",
        "![Backtest](graficos/backtest_proyeccion.png)",
        "",
        f"Se probaron tres métodos proyectando cada año cerrado desde {mes}, con datos disponibles a esa fecha. "
        f"El de menor error, **{mejor.metodo.replace('_', ' ')}**, se equivocó en promedio {pct(mejor.error_medio_abs)} "
        f"(máximo {pct(mejor.error_maximo_abs)}) en {int(mejor.ejercicios)} ejercicios. El rango de la proyección "
        "aplica los errores mínimo y máximo de ese backtest: dice cuánto se equivocó antes, no es un intervalo de "
        "confianza formal.",
        "",
        tabla_md(r.resumen_backtest.assign(
            error_medio_abs=lambda d: d.error_medio_abs.map(pct),
            error_maximo_abs=lambda d: d.error_maximo_abs.map(pct),
            sesgo_medio=lambda d: d.sesgo_medio.map(lambda v: pct(v, True)),
        ).rename(columns={"metodo": "Método", "ejercicios": "Ejercicios", "error_medio_abs": "Error medio",
                          "error_maximo_abs": "Error máximo", "sesgo_medio": "Sesgo medio"})),
        "",
        "## Limitaciones",
        "",
        "- El devengado registra la obligación de pago, no el pago: la deuda flotante se mide como devengado menos pagado.",
        "- El IPC del último mes puede revisarse; los montos reales cambian en consecuencia.",
        "- La proyección supone que lo que resta del año sigue el patrón real promedio de los 3 ejercicios "
        "anteriores y que la inflación mensual de los últimos 3 meses se mantiene.",
        "- Comparar organismos entre años está limitado por las reestructuraciones de ministerios.",
    ]
    return "\n".join(lineas) + "\n"
