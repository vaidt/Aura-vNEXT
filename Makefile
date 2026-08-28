# Aura vNEXT.
# Python 3.11 standard library only; no third-party dependencies
# (ADR-0002 for the governance baseline, ADR-0004 for M0).

PYTHON ?= python3

.PHONY: check structure register fixtures independence test verify help

help:
	@echo "make check         run every gate (structure, register, fixtures, tests, independence)"
	@echo "make structure     validate the repository structure and ADR index"
	@echo "make register      validate the module transfer register"
	@echo "make fixtures      check the M0 conformance vectors match the implementation"
	@echo "make test          run the full test suite"
	@echo "make independence  verify the reference package in an isolated environment"
	@echo "make verify        verify the reference evidence package"

check: structure register fixtures test independence

structure:
	$(PYTHON) tools/validate_structure.py

register:
	$(PYTHON) tools/validate_register.py

fixtures:
	$(PYTHON) tools/build_m0_fixtures.py --check

test:
	$(PYTHON) -m unittest discover -s tests -v

independence:
	$(PYTHON) tools/independence_check.py

verify:
	$(PYTHON) -m app.verifier evidence/examples/aura-evidence-loan-001 --json
