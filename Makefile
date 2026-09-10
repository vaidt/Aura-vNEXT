# Aura vNEXT.
# Python 3.11 standard library only; no third-party dependencies
# (ADR-0002 for the governance baseline, ADR-0004 for M0).

PYTHON ?= python3

.PHONY: check structure register fixtures independence product test verify inspect record help

help:
	@echo "make check         run every gate (structure, register, fixtures, tests, independence, product)"
	@echo "make structure     validate the repository structure and ADR index"
	@echo "make register      validate the module transfer register"
	@echo "make fixtures      check the M0 conformance vectors match the implementation"
	@echo "make test          run the full test suite"
	@echo "make independence  verify the reference package in an isolated environment"
	@echo "make product       run the product loop end to end: event -> package -> verdict"
	@echo "make verify        verify the reference evidence package"
	@echo "make inspect       describe the reference evidence package"
	@echo "make record        record a demonstration package into ./build/"

check: structure register fixtures test independence product

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

product:
	$(PYTHON) tools/product_loop_check.py

verify:
	$(PYTHON) -m app.aura verify evidence/examples/aura-evidence-loan-001

inspect:
	$(PYTHON) -m app.aura package evidence/examples/aura-evidence-loan-001

record:
	$(PYTHON) tools/product_loop_check.py --keep build/aura-evidence-loan-001
