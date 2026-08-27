# Aura vNEXT — Genesis baseline.
# Python 3.11 standard library only; no third-party dependencies (ADR-0002, OQ-4).

PYTHON ?= python3

.PHONY: check structure register test help

help:
	@echo "make check      run every baseline check (structure, register, tests)"
	@echo "make structure  validate the repository structure and ADR index"
	@echo "make register   validate the module transfer register"
	@echo "make test       run the governance invariant test suite"

check: structure register test

structure:
	$(PYTHON) tools/validate_structure.py

register:
	$(PYTHON) tools/validate_register.py

test:
	$(PYTHON) -m unittest discover -s tests -v
