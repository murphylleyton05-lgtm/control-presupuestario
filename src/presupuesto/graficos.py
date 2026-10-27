"""Gráficos estáticos para el informe (PNG).

Un solo color de énfasis (el año en curso o la serie principal) y gris para el
contexto; en las variaciones, azul para suba y rojo para baja, siempre con el
valor escrito al lado: el color nunca es la única forma de leer el dato.
Paleta validada con chequeo de daltonismo y contraste (azul #2a78d6 / rojo #e34948).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

AZUL, ROJO = "#2a78d6", "#e34948"
GRIS_CONTEXTO, GRILLA = "#b9b8b2", "#e7e6e2"
TEXTO, TEXTO_SECUNDARIO, FONDO = "#0b0b0b", "#52514e", "#fcfcfb"
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                "septiembre", "octubre", "noviembre", "diciembre"]
FUENTE = "Fuente: Presupuesto Abierto (Secretaría de Hacienda) e INDEC."
ANCHO = 8.5
ETIQUETAS_CORTAS = {"Servicio de la deuda y disminución de otros pasivos": "Servicio de la deuda",
                    "Servicio de la Deuda Pública (intereses y gastos)": "Servicio de la deuda pública"}


def porcentaje(valor: float, signo: bool = False) -> str:
    """76.04 -> '76,0 %' (con signo: '+76,0 %')."""
    return (f"{valor:+.1f}" if signo else f"{valor:.1f}").replace(".", ",") + " %"


def _figura(alto: float, izquierda: float):
    """Márgenes fijos en pulgadas: título y fuente quedan siempre en el mismo lugar."""
    fig, ax = plt.subplots(figsize=(ANCHO, alto), dpi=150)
    fig.subplots_adjust(top=1 - 1.0 / alto, bottom=0.6 / alto, left=izquierda / ANCHO, right=1 - 0.5 / ANCHO)
    return fig, ax


def _estilo(ax, titulo: str, subtitulo: str) -> None:
    fig = ax.figure
    alto = fig.get_figheight()
    ax.set_facecolor(FONDO)
    fig.set_facecolor(FONDO)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(GRIS_CONTEXTO)
    ax.tick_params(colors=TEXTO_SECUNDARIO, labelsize=9, length=0)
    fig.text(0.02, 1 - 0.22 / alto, titulo, fontsize=13, fontweight="bold", color=TEXTO, va="top")
    fig.text(0.02, 1 - 0.52 / alto, subtitulo, fontsize=9.5, color=TEXTO_SECUNDARIO, va="top")
    fig.text(0.02, 0.12 / alto, FUENTE, fontsize=7.5, color=TEXTO_SECUNDARIO)


def _etiqueta(nombre: str, largo: int = 44) -> str:
    nombre = ETIQUETAS_CORTAS.get(nombre, nombre)
    return nombre if len(nombre) <= largo else nombre[: largo - 1] + "…"


def curva_de_ejecucion(curva: pd.DataFrame, ejercicio: int, mes_corte: int, destino: Path) -> None:
    fig, ax = _figura(4.9, 0.6)
    previos = curva[curva.ejercicio < ejercicio]
    for _, g in previos.groupby("ejercicio"):
        ax.plot(g.mes, g.pct_acumulado, color=GRIS_CONTEXTO, linewidth=1.2, zorder=1)
    actual = curva[(curva.ejercicio == ejercicio) & (curva.mes <= mes_corte)]
    ax.plot(actual.mes, actual.pct_acumulado, color=AZUL, linewidth=2.4, zorder=3, marker="o", markersize=4)
    ultimo = actual.iloc[-1]
    ax.annotate(f"{ejercicio}: {porcentaje(ultimo.pct_acumulado)}", (ultimo.mes, ultimo.pct_acumulado),
                xytext=(8, 0), textcoords="offset points", color=TEXTO, fontsize=9.5, fontweight="bold", va="center")
    fin_previos = previos[previos.mes == 12]
    desde, hasta = previos.ejercicio.min(), previos.ejercicio.max()
    ax.annotate(f"{desde}–{hasta}", (12, fin_previos.pct_acumulado.median()),
                xytext=(8, 0), textcoords="offset points", color=TEXTO_SECUNDARIO, fontsize=9, va="center")
    ax.set_xticks(range(1, 13), MESES)
    ax.set_xlim(0.6, 12.9)
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f} %")
    ax.grid(axis="y", color=GRILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    al_corte = previos[previos.mes == mes_corte].pct_acumulado
    if ultimo.pct_acumulado > al_corte.max():
        titulo = f"El gasto {ejercicio} avanza más rápido que en cualquier año desde {desde}"
    elif ultimo.pct_acumulado < al_corte.min():
        titulo = f"El gasto {ejercicio} avanza más lento que en cualquier año desde {desde}"
    else:
        titulo = f"Ritmo de ejecución {ejercicio} vs. {desde}–{hasta}"
    _estilo(ax, titulo, "Devengado acumulado como % del crédito vigente, mes a mes")
    fig.savefig(destino, facecolor=FONDO)
    plt.close(fig)


def ejecucion_por_jurisdiccion(tabla: pd.DataFrame, ejercicio: int, mes_corte: int, destino: Path,
                               cantidad: int = 12) -> None:
    datos = tabla.dropna(subset=["pct_ejecucion_anterior"]).head(cantidad).iloc[::-1].reset_index(drop=True)
    fig, ax = _figura(0.42 * len(datos) + 1.9, 3.1)
    for i, fila in datos.iterrows():
        ax.plot([fila.pct_ejecucion_anterior, fila.pct_ejecucion], [i, i], color=GRILLA, linewidth=2.5, zorder=1)
        # La etiqueta va del lado de afuera del punto azul, para no pisar el gris.
        derecha = fila.pct_ejecucion >= fila.pct_ejecucion_anterior
        ax.annotate(porcentaje(fila.pct_ejecucion).replace(",0 %", " %"), (fila.pct_ejecucion, i),
                    xytext=(8 if derecha else -8, 0), textcoords="offset points", va="center",
                    ha="left" if derecha else "right", fontsize=8, color=TEXTO)
    ax.scatter(datos.pct_ejecucion_anterior, datos.index, color=GRIS_CONTEXTO, s=42, zorder=2, label=str(ejercicio - 1))
    ax.scatter(datos.pct_ejecucion, datos.index, color=AZUL, s=48, zorder=3, label=str(ejercicio),
               edgecolor=FONDO, linewidth=1.5)
    ax.set_yticks(datos.index, [_etiqueta(n) for n in datos.nombre], fontsize=8.5, color=TEXTO)
    minimo = min(datos.pct_ejecucion.min(), datos.pct_ejecucion_anterior.min())
    maximo = max(datos.pct_ejecucion.max(), datos.pct_ejecucion_anterior.max())
    ax.set_xlim(minimo - 6, maximo + 6)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f} %")
    ax.grid(axis="x", color=GRILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=8.5,
              labelcolor=TEXTO_SECUNDARIO, handletextpad=0.3, borderaxespad=0.2)
    _estilo(ax, f"Ejecución por organismo a fin de {MESES_LARGOS[mes_corte - 1]}: {ejercicio} vs. {ejercicio - 1}",
            f"% del crédito vigente devengado · los {len(datos)} organismos con más presupuesto comparables")
    fig.savefig(destino, facecolor=FONDO)
    plt.close(fig)


def variacion_real(tabla: pd.DataFrame, titulo: str, subtitulo: str, destino: Path,
                   participacion_minima: float = 0.005) -> None:
    """Barras horizontales de variación real. Se excluyen las partidas chicas
    (menos del 0,5 % del gasto del año anterior): su % se dispara por base baja."""
    total = tabla.real_anterior.sum()
    datos = tabla[tabla.real_anterior >= participacion_minima * total].sort_values("variacion_real_pct")
    datos = datos.reset_index(drop=True)
    fig, ax = _figura(0.36 * len(datos) + 1.9, 3.1)
    ax.barh(datos.index, datos.variacion_real_pct, height=0.62,
            color=[AZUL if v >= 0 else ROJO for v in datos.variacion_real_pct])
    for i, v in datos.variacion_real_pct.items():
        ax.annotate(porcentaje(v, signo=True), (v, i), xytext=(5 if v >= 0 else -5, 0), textcoords="offset points",
                    ha="left" if v >= 0 else "right", va="center", fontsize=8, color=TEXTO)
    ax.axvline(0, color=TEXTO_SECUNDARIO, linewidth=0.8)
    ax.set_yticks(datos.index, [_etiqueta(n) for n in datos.nombre], fontsize=8.5, color=TEXTO)
    margen = max(abs(datos.variacion_real_pct.min()), abs(datos.variacion_real_pct.max())) * 1.35
    ax.set_xlim(-margen, margen)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f} %")
    ax.grid(axis="x", color=GRILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    _estilo(ax, titulo, subtitulo)
    fig.savefig(destino, facecolor=FONDO)
    plt.close(fig)


def backtest(bt: pd.DataFrame, mes_corte: int, destino: Path) -> None:
    nombres = {"lineal": "Lineal (acumulado × 12 / meses)",
               "estacional_nominal": "Estacionalidad nominal (3 años)",
               "estacional_real": "Estacionalidad real (3 años)"}
    error_medio = bt.assign(a=bt.error_pct.abs()).groupby("metodo").a.mean().sort_values(ascending=False)
    fig, ax = _figura(3.7, 2.6)
    fig.subplots_adjust(right=1 - 1.6 / ANCHO)
    for i, metodo in enumerate(error_medio.index):
        g = bt[bt.metodo == metodo]
        ax.scatter(g.error_pct, [i] * len(g), color=AZUL, s=40, alpha=0.85, edgecolor=FONDO, linewidth=1)
        # El error medio va en una columna fija a la derecha del gráfico.
        ax.annotate(f"error medio {porcentaje(error_medio[metodo])}", (1.02, i), xycoords=("axes fraction", "data"),
                    va="center", fontsize=8.5, color=TEXTO)
    ax.axvline(0, color=TEXTO_SECUNDARIO, linewidth=0.8)
    ax.set_yticks(range(len(error_medio)), [nombres[m] for m in error_medio.index], fontsize=8.5, color=TEXTO)
    ax.set_ylim(-0.6, len(error_medio) - 0.4)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:+.0f} %".replace("+0 %", "0 %"))
    ax.grid(axis="x", color=GRILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    años = f"{bt.ejercicio.min()}–{bt.ejercicio.max()}"
    _estilo(ax, f"¿Qué método proyecta mejor el cierre desde {MESES_LARGOS[mes_corte - 1]}?",
            f"Error de la proyección vs. el devengado real de cada año ({años}); cada punto es un año")
    fig.savefig(destino, facecolor=FONDO)
    plt.close(fig)
