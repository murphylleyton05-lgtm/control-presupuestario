PY := .venv/bin/python

.PHONY: instalar test todo informe

instalar:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

test:
	$(PY) -m pytest -q

# Descarga, procesa, controla, analiza y exporta con los datos del día.
todo:
	$(PY) -m presupuesto.cli todo

# Solo regenera informe y gráficos con lo ya descargado.
informe:
	$(PY) -m presupuesto.cli informe
