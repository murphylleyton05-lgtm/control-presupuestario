# Registro de decisiones

### D1. Conciliar contra las publicaciones oficiales antes de analizar

Un informe de control de gestión que no cierra contra los números oficiales no sirve, por bueno que sea el análisis. La base detallada se suma por ejercicio y se compara con dos publicaciones de Presupuesto Abierto: la "Serie anual de gastos" y el archivo "Total Presupuesto y ejecución".

**Hallazgo.** Las dos publicaciones oficiales no coinciden entre sí en 2018-2025. La base detallada coincide al peso con la serie anual en 9 de 10 ejercicios cerrados. En 2024 queda 0,18 % por debajo: el archivo detallado de 2024 es de julio de 2025 y la serie se actualizó después. Las diferencias se publican en el informe en vez de ajustarse para que "cierren".

### D2. Se analiza hasta el último mes completo

Los datos se actualizan a diario: el 23 de octubre, octubre tiene 23 días cargados. Compararlo con octubres completos de otros años haría parecer que el gasto se frena. El mes de corte sale de la fecha de actualización del propio archivo.

### D3. El vigente se reconstruye acumulando modificaciones

En el archivo mensual, `credito_vigente` del mes 1 es el crédito inicial y los meses siguientes traen solo las modificaciones del mes. El vigente a septiembre es la suma de enero a septiembre. Se verificó contra el total oficial de 2026: diferencia 0.

### D4. Comparaciones entre años por código, no por nombre

Los ministerios cambian de nombre y de estructura entre gestiones (la jurisdicción 50 fue "Hacienda y Finanzas Públicas", "Hacienda" y "Economía"). También cambian funciones: "Servicio de la Deuda Pública" pasó a "... (intereses y gastos)" en 2026. Comparar por nombre partía la deuda en dos filas sin dato. Se compara por código y se muestra el nombre más reciente. Un organismo que no existía el año anterior con el mismo código queda fuera de la comparación, en vez de compararse contra cero.

### D5. Variaciones en términos reales, con el IPC del mes

Con una inflación anual de entre 25 % y 211 % según el año (2017-2025), comparar pesos corrientes no dice nada. Cada mes se deflacta con su IPC nacional y se expresa en pesos del mes de corte. En los gráficos de variación se excluyen las partidas de menos del 0,5 % del gasto: "Otros gastos" sube más del 3.000 % porque parte de una base casi nula, y eso no es un hallazgo.

### D6. El método de proyección se elige por backtest, no por intuición

Para proyectar el cierre se probaron tres métodos sobre cada ejercicio cerrado de 2019 a 2025, usando solo información disponible a septiembre de ese año. El lineal (acumulado × 12/9) subestima siempre, porque diciembre pesa más: 10,1 % de error medio. La estacionalidad nominal se distorsiona en años de inflación alta: 4,9 %. La estacionalidad en términos reales es la mejor: 3,3 % de error medio y 5,9 % de máximo. El rango publicado son los errores mínimo y máximo del backtest, no un intervalo de confianza: con 7 años no da para más.

### D7. Agregar antes de exportar, y Power BI con un CSV de hechos

Los CSV originales pesan entre 316 y 564 MB por año (5,25 GB en total), con 53 a 57 columnas. Se agregan a las 10 dimensiones que usa el análisis, quedan en Parquet (unos 5 MB por año) y se procesan con DuckDB. El modelo para Power BI es un esquema estrella: una tabla de hechos mensual (345.000 filas desde 2022) y siete dimensiones.

### D8. Sin funciones de inteligencia de tiempo en DAX

`dim_fecha` tiene un registro por mes. Las funciones DATESYTD y SAMEPERIODLASTYEAR esperan una tabla de fechas diaria. Los acumulados se calculan filtrando ejercicio y mes de forma explícita, y el resultado se verificó replicando la lógica sobre los CSV: da las mismas cifras que el informe.
