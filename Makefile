PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_UVICORN := $(VENV)/bin/uvicorn

.PHONY: install run seed test demo assets

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install -e ".[dev]"

demo: install seed

run:
	$(VENV_UVICORN) agent_activity_graph.api.app:create_app --factory --reload

seed:
	$(VENV_PYTHON) -m agent_activity_graph.demo.seed

assets:
	$(VENV_PYTHON) scripts/generate_assets.py

test:
	$(VENV_PYTHON) -m pytest -q
