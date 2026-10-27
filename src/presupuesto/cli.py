"""Línea de comandos: `presupuesto <comando>`.

    presupuesto todo        descarga, procesa, controla, analiza y exporta (lo normal)
    presupuesto descargar   baja los archivos oficiales a data/crudo/
    presupuesto procesar    convierte cada ejercicio a Parquet en data/procesado/
    presupuesto informe     controles + análisis + gráficos en resultados/
    presupuesto modelo      tablas del modelo estrella para Power BI en modelo/
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import carga, controles, fuentes, indicadores, informe, modelo


def _rutas(args: argparse.Namespace) -> dict[str, Path]:
    raiz = Path(args.raiz)
    return {"crudo": raiz / "data" / "crudo", "procesado": raiz / "data" / "procesado",
            "tmp": raiz / "data" / "tmp", "resultados": raiz / "resultados", "modelo": raiz / "modelo"}


def cmd_descargar(args, rutas) -> None:
    print("Descargando de Presupuesto Abierto e INDEC...")
    fuentes.descargar_todo(rutas["crudo"], list(range(args.desde, args.ejercicio + 1)), args.ejercicio)


def cmd_procesar(args, rutas) -> None:
    for ejercicio in range(args.desde, args.ejercicio + 1):
        destino = rutas["procesado"] / f"ejecucion_{ejercicio}.parquet"
        if destino.exists() and ejercicio != args.ejercicio and not args.forzar:
            continue
        filas = carga.zip_a_parquet(rutas["crudo"] / f"credito-mensual-{ejercicio}.zip", destino, rutas["tmp"])
        print(f"  {ejercicio}: {filas:,} filas agregadas".replace(",", "."))


def _entradas(rutas):
    con = carga.conexion(rutas["procesado"])
    totales = carga.leer_totales(rutas["crudo"] / "totales-de-presupuesto.zip")
    serie = carga.leer_serie_anual(rutas["crudo"] / "serie_pib_anual.csv")
    ipc = carga.leer_ipc(rutas["crudo"] / "ipc.csv")
    return con, totales, serie, ipc


def cmd_informe(args, rutas) -> None:
    con, totales, serie, ipc = _entradas(rutas)
    resultados = informe.calcular(con, totales, serie, ipc, args.ejercicio)
    problemas = controles.problemas_de_calidad(resultados.calidad)
    if problemas:
        sys.exit(f"Hay {problemas} problemas de calidad en los datos: revisá resultados antes de publicar.")
    informe.guardar_tablas(resultados, rutas["resultados"] / "tablas")
    informe.generar_graficos(resultados, rutas["resultados"] / "graficos")
    (rutas["resultados"] / "informe.md").write_text(informe.markdown(resultados), encoding="utf-8")
    print(f"Informe: {rutas['resultados'] / 'informe.md'} (corte: {resultados.mes_corte}/{args.ejercicio})")


def cmd_modelo(args, rutas) -> None:
    con, _, _, ipc = _entradas(rutas)
    mes_corte, _ = indicadores.mes_de_corte(con, args.ejercicio)
    filas = modelo.exportar(con, ipc, rutas["modelo"], desde=args.desde_modelo,
                            ejercicio_en_curso=args.ejercicio, mes_corte=mes_corte)
    for tabla, n in filas.items():
        print(f"  {tabla}: {n:,} filas".replace(",", "."))


def cmd_todo(args, rutas) -> None:
    for paso in (cmd_descargar, cmd_procesar, cmd_informe, cmd_modelo):
        paso(args, rutas)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="presupuesto", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raiz", default=".", help="carpeta del proyecto (default: la actual)")
    parser.add_argument("--ejercicio", type=int, default=date.today().year, help="ejercicio en curso")
    parser.add_argument("--desde", type=int, default=2016, help="primer ejercicio a descargar y analizar")
    parser.add_argument("--desde-modelo", type=int, default=2022, help="primer ejercicio del modelo de Power BI")
    parser.add_argument("--forzar", action="store_true", help="reprocesa también los ejercicios cerrados")
    comandos = {"todo": cmd_todo, "descargar": cmd_descargar, "procesar": cmd_procesar,
                "informe": cmd_informe, "modelo": cmd_modelo}
    parser.add_argument("comando", choices=comandos)
    args = parser.parse_args(argv)
    comandos[args.comando](args, _rutas(args))


if __name__ == "__main__":
    main()
