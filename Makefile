.PHONY: all test test-contracts test-python lint slither demo experiments clean

PYTHON ?= .venv/Scripts/python.exe
PYTEST ?= .venv/Scripts/pytest.exe
FORGE ?= forge

all: test

test: test-contracts test-python

test-contracts:
	$(FORGE) test -vv

test-python:
	$(PYTEST) tests/ -v

experiments:
	$(PYTHON) -m experiments.run_experiments

lint:
	$(FORGE) fmt --check
	$(PYTHON) -m pycodestyle ledger/ sim/ tests/ || true

slither:
	$(PYTHON) -m slither contracts/ --solc-remaps @openzeppelin/=lib/openzeppelin-contracts/

demo:
	$(PYTHON) -m sim.demo


clean:
	$(FORGE) clean || true
	git clean -Xdf data/
