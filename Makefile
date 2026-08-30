VENV := .venv/bin

.PHONY: install build check test all clean

install:
	uv venv
	uv pip install -e ".[dev]"

build:
	$(VENV)/python -m nificac build

check:
	$(VENV)/python -m nificac check

test:
	$(VENV)/python -m pytest -q

all: build test check

clean:
	rm -rf .venv .pytest_cache **/__pycache__
