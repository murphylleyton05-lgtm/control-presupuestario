"""Descarga de las fuentes oficiales, con caché local.

- Presupuesto Abierto (Secretaría de Hacienda): ejecución de gastos de la
  Administración Pública Nacional, mes por mes y partida por partida, y los
  totales anuales oficiales que se usan para conciliar. Licencia CC BY 4.0.
- INDEC vía datos.gob.ar: IPC nacional, nivel general, base dic-2016 = 100.

Los importes de Presupuesto Abierto están en millones de pesos corrientes.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

REPO = "https://dgsiaf-repo.mecon.gob.ar/repository/pa/datasets"
URL_TOTALES = f"{REPO}/totales-de-presupuesto.zip"
URL_SERIE_ANUAL = f"{REPO}/serie_pib_anual.csv"
URL_IPC = ("https://infra.datos.gob.ar/catalog/sspm/dataset/145/distribution/145.3/download/"
           "indice-precios-al-consumidor-nivel-general-base-diciembre-2016-mensual.csv")

# Algunos servidores del Estado rechazan pedidos sin un User-Agent de navegador.
_CABECERAS = {"User-Agent": "Mozilla/5.0 (control-presupuestario; datos abiertos)"}


def url_credito_mensual(ejercicio: int) -> str:
    return f"{REPO}/{ejercicio}/credito-mensual-{ejercicio}.zip"


def descargar(url: str, destino: Path, forzar: bool = False) -> Path:
    """Baja `url` a `destino` si no existe (o si `forzar`). Escribe a un archivo
    temporal y lo renombra al final: una descarga cortada no deja un zip roto."""
    if destino.exists() and not forzar:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    pedido = urllib.request.Request(url, headers=_CABECERAS)
    with urllib.request.urlopen(pedido, timeout=300) as respuesta, parcial.open("wb") as archivo:
        while bloque := respuesta.read(1 << 20):
            archivo.write(bloque)
    parcial.replace(destino)
    return destino


def descargar_todo(carpeta: Path, ejercicios: list[int], ejercicio_en_curso: int) -> None:
    """El ejercicio en curso y los totales se actualizan a diario: se bajan
    siempre. Los ejercicios cerrados se bajan una sola vez."""
    for ejercicio in ejercicios:
        forzar = ejercicio == ejercicio_en_curso
        ruta = descargar(url_credito_mensual(ejercicio), carpeta / f"credito-mensual-{ejercicio}.zip", forzar)
        print(f"  {ruta.name}: {ruta.stat().st_size / 1e6:.1f} MB")
    descargar(URL_TOTALES, carpeta / "totales-de-presupuesto.zip", forzar=True)
    descargar(URL_SERIE_ANUAL, carpeta / "serie_pib_anual.csv", forzar=True)
    descargar(URL_IPC, carpeta / "ipc.csv", forzar=True)
