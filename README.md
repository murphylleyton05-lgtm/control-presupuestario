# Control presupuestario del Estado nacional

Informe de control de gestión sobre la ejecución del presupuesto de la Administración Pública Nacional: cuánto se gastó de lo presupuestado, en qué, cómo cambió en términos reales y cuánto se va a gastar al cierre del año. Usa los datos oficiales de [Presupuesto Abierto](https://www.presupuestoabierto.gob.ar/sici/datos-abiertos) (Secretaría de Hacienda) y el IPC del INDEC: 11 ejercicios, mes por mes y partida por partida.

> Datos al **23/10/2026**, analizados hasta septiembre (último mes completo). Todo se regenera con un comando: `presupuesto todo`. Informe completo: [`resultados/informe.md`](resultados/informe.md).

![Curva de ejecución](resultados/graficos/curva_ejecucion.png)

## Hallazgos (enero-septiembre 2026)

| | |
|---|---|
| **El gasto avanza más rápido que en cualquier año desde 2016** | Se devengó el **76,0 %** del crédito vigente. En 2016-2025, al mismo mes, se había ejecutado entre 64,6 % y 73,5 %. |
| **En términos reales, el gasto total no cambió, pero sí su composición** | El total quedó **−0,3 %** real contra 2025. Los intereses de la deuda suben **+27,8 %**, la inversión física (bienes de uso) cae **−23,1 %** y los sueldos **−4,2 %**. |
| **El presupuesto casi no se modificó** | El vigente está solo **+3,0 %** por encima del aprobado; en 2025 iba +32,7 % al mismo mes. |
| **El crédito vigente no alcanza al ritmo actual** | La proyección de cierre es **$ 161,2 billones** (rango $ 154,0 a $ 171,3 billones): 105,7 % del vigente actual. Incluso el extremo bajo supera el crédito disponible. |
| **Las fuentes oficiales no coinciden entre sí** | Dos publicaciones de Presupuesto Abierto difieren hasta un 5,9 % en el devengado de 2018-2025. La base de este proyecto coincide al peso con una de ellas en 9 de 10 años. |

![Variación real por objeto del gasto](resultados/graficos/variacion_real_objeto.png)

## Qué hace

```
Presupuesto Abierto (11 CSV, 316-564 MB c/u) ─┐
INDEC (IPC mensual) ───────────────────────────┼─► descarga ─► Parquet (DuckDB) ─► controles ─► análisis ─► informe + gráficos
Totales oficiales (2 publicaciones) ───────────┘                                      │                     └► modelo estrella para Power BI
                                                                                       └► conciliación contra las cifras oficiales
```

1. **Descarga** los archivos oficiales (los ejercicios cerrados, una sola vez).
2. **Agrega** cada ejercicio a las dimensiones del análisis y lo guarda en Parquet: de 5,25 GB de CSV a 52 MB.
3. **Controla** antes de analizar: concilia contra dos publicaciones oficiales y revisa meses inválidos, claves nulas y presupuesto cargado fuera de enero. Si hay problemas de calidad, el informe no se genera.
4. **Analiza** como un área de control de gestión:
   - ritmo de ejecución contra la historia;
   - ejecución por organismo contra el año anterior;
   - variación real por objeto del gasto y por función;
   - deuda flotante (devengado y no pagado);
   - modificaciones presupuestarias.
5. **Proyecta el cierre** con tres métodos, elegidos por backtest sobre 2019-2025.
6. **Exporta** un modelo estrella (hechos + 7 dimensiones) para armar el tablero en Power BI.

## La proyección está validada

Cada método se probó proyectando cada año cerrado desde septiembre, con la información que había en ese momento:

![Backtest](resultados/graficos/backtest_proyeccion.png)

- **Lineal (acumulado × 12/9):** subestima siempre, porque diciembre pesa más que el promedio (aguinaldo, cierres de año).
- **Estacionalidad en términos reales:** es el mejor, con 3,3 % de error medio y 5,9 % de máximo. Es el que se usa.

## Tablero en Power BI

El modelo para Power BI está en [`modelo/modelo_powerbi.zip`](modelo/): una tabla de hechos mensual de 345.000 filas y 7 dimensiones. Las medidas DAX están en [`powerbi/medidas.dax`](powerbi/medidas.dax) y la guía paso a paso en [`powerbi/GUIA.md`](powerbi/GUIA.md). Incluye valores de control para verificar que el tablero da lo mismo que el informe.

## Cómo correrlo

```bash
python -m venv .venv && . .venv/bin/activate      # en Windows: .venv\Scripts\activate
pip install -e ".[dev]"
presupuesto todo          # descarga (~185 MB la primera vez), procesa, controla, analiza y exporta
pytest                    # 18 tests con datos de prueba chicos, sin internet
```

## Estructura

```
src/presupuesto/
  fuentes.py      descarga de Presupuesto Abierto e INDEC, con caché
  carga.py        CSV -> Parquet con DuckDB, lectura de totales e IPC
  controles.py    conciliación contra publicaciones oficiales y calidad de datos
  indicadores.py  corte, ritmo de ejecución, ejecución por organismo, variación real
  proyeccion.py   métodos de proyección y backtest
  informe.py      tablas, gráficos e informe en Markdown (sin cifras escritas a mano)
  graficos.py     gráficos con paleta validada para daltonismo
  modelo.py       modelo estrella para Power BI
resultados/       informe, gráficos y tablas de la última corrida
powerbi/          medidas DAX y guía del tablero
docs/decisiones.md  por qué está hecho así
```

## Limitaciones

- El devengado registra la obligación de pago, no el pago. La deuda flotante se aproxima como devengado menos pagado.
- La proyección supone que el resto del año sigue el patrón real de los 3 años anteriores y que se mantiene la inflación de los últimos 3 meses. Con 7 años de backtest, el rango es indicativo.
- Los ministerios se reorganizan entre gestiones: un organismo nuevo no tiene contra qué compararse.

## Uso de IA en el desarrollo

El código se escribió con asistencia de Claude Code. Las decisiones y sus motivos están en [`docs/decisiones.md`](docs/decisiones.md); los cálculos tienen tests y las cifras se verificaron contra las publicaciones oficiales.
