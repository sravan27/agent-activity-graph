PYTHON ?= python3
VENV ?= .venv
FILE ?= examples/traces/openai_agents_invoice_review.json
LOCAL_TRACE_FILE ?= examples/traces/ollama_local_invoice_review.json
OLLAMA_MODEL ?= gemma3:4b
VENV_PYTHON := $(VENV)/bin/python
VENV_UVICORN := $(VENV)/bin/uvicorn

.PHONY: install run seed test demo assets ingest-trace generate-local-trace ingest-local-trace

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

ingest-trace:
	$(VENV_PYTHON) scripts/ingest_trace.py --file $(FILE)

generate-local-trace:
	$(VENV_PYTHON) scripts/generate_local_trace.py --output $(LOCAL_TRACE_FILE) --model $(OLLAMA_MODEL)

ingest-local-trace:
	$(VENV_PYTHON) scripts/ingest_trace.py --file $(LOCAL_TRACE_FILE)

test:
	$(VENV_PYTHON) -m pytest -q
