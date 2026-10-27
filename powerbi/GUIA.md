# Guía para armar el tablero en Power BI Desktop

Tiempo estimado: 2 a 3 horas. Power BI Desktop es gratis (Windows). Las medidas DAX están en [`medidas.dax`](medidas.dax).

> Las medidas se escribieron para este modelo pero no se pudieron probar en Power BI desde el entorno donde se generaron los datos. Si alguna da error, copiá el mensaje y la fórmula: casi siempre es un nombre de columna o de tabla.

## 1. Datos

1. Descomprimí `modelo/modelo_powerbi.zip` (8 CSV). Para regenerarlos con datos del día: `presupuesto todo`.
2. **Antes de importar:** *Archivo > Opciones y configuración > Opciones > Archivo actual > Configuración regional* → **Inglés (Estados Unidos)**. Los CSV usan punto decimal; con la configuración de Argentina, `112314.62` se lee como 11.231.462.
3. *Obtener datos > Texto/CSV*, uno por uno. En Power Query (*Transformar datos*):
   - Todas las columnas `*_key` y `clave` → tipo **Texto**. `3.1` es un código, no un número.
   - `fecha` → Fecha; importes (`presupuestado`, `vigente_movimiento`, `comprometido`, `devengado`, `pagado`) → Número decimal; `mes_completo` → Verdadero/falso.

## 2. Modelo (vista de modelo)

Relaciones de varios a uno, dirección de filtro simple, desde `hechos_ejecucion` hacia cada dimensión:

| hechos_ejecucion | → | dimensión |
|---|---|---|
| `fecha` | → | `dim_fecha[fecha]` |
| `jurisdiccion_key` | → | `dim_jurisdiccion[clave]` |
| `programa_key` | → | `dim_programa[clave]` |
| `funcion_key` | → | `dim_funcion[clave]` |
| `objeto_key` | → | `dim_objeto[clave]` |
| `fuente_key` | → | `dim_fuente[clave]` |
| `caracter_key` | → | `dim_caracter[clave]` |

Ocultá las columnas `*_key` y los importes crudos: en el informe se usan solo las medidas.

## 3. Medidas

Creá las medidas de [`medidas.dax`](medidas.dax) en la tabla `hechos_ejecucion`. Formatos sugeridos:
- Importes: número sin decimales, con separador de miles. Están en millones: en las tarjetas aclará "millones de $".
- `% ...` y `Variación real interanual`: porcentaje con 1 decimal.

## 4. Páginas

**Filtro de todas las páginas:** `dim_fecha[mes_completo] = Verdadero`. El mes en curso viene parcial y no se compara con meses completos.

1. **Resumen ejecutivo**
   - Segmentadores: `dim_fecha[ejercicio]` y `dim_fecha[mes_nombre]` (selección única).
   - Tarjetas: Crédito vigente, Devengado acumulado, % Ejecución, Diferencia vs año anterior (pp), Deuda flotante, Variación real interanual.
   - Gráfico de líneas: eje X `dim_fecha[mes]`, valor `% Ejecución`, leyenda `dim_fecha[ejercicio]`. Para que cada mes muestre su acumulado, este visual **no** debe quedar filtrado por el segmentador de mes (*Formato > Editar interacciones*).
2. **Por organismo**
   - Matriz: filas `dim_jurisdiccion[jurisdiccion_desc]` → `dim_programa[programa_desc]` (con drill-down). Valores: Crédito vigente, Devengado acumulado, % Ejecución, % Ejecución año anterior, Diferencia vs año anterior (pp), Deuda flotante.
   - Formato condicional en *Diferencia (pp)*: íconos de flecha más color. Así el desvío no depende solo del color.
3. **Qué y para qué se gasta**
   - Barras horizontales: `dim_objeto[inciso_desc]` con `Variación real interanual`.
   - Barras horizontales: `dim_funcion[funcion_desc]` con `Variación real interanual`. Filtro de nivel visual para dejar afuera partidas chicas: `Devengado real acumulado año anterior` mayor a 0,5 % del total.
4. **Proyección y calidad**
   - Importá `resultados/tablas/proyeccion_cierre.csv` y `backtest_proyeccion.csv`: tarjeta con la proyección y su rango, y tabla del error por método.
   - Importá `resultados/tablas/conciliacion.csv`: tabla de conciliación contra las publicaciones oficiales. Muestra que los números cierran antes de mostrar conclusiones.

## 5. Control de que está bien armado

Con el filtro en **septiembre 2026**, el tablero tiene que mostrar los mismos valores que [`resultados/informe.md`](../resultados/informe.md):
- **Crédito vigente:** 152,5 billones (152.474.969 millones).
- **% Ejecución:** 76,0 %.
- **Variación real interanual:** −0,3 %.

Si no coinciden, revisá la configuración regional (paso 1.2) y las relaciones.

## 6. Publicar

- Con cuenta laboral o educativa: *Publicar > Publicar en la web*. Los datos son públicos, así que se puede.
- Sin esa cuenta: guardá el `.pbix` en el repo, sacá capturas de cada página para el README y grabá un video corto recorriendo el tablero.
