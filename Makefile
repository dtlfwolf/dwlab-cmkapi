SHELL := /bin/bash

ROOT := $(abspath $(CURDIR))
PACKAGE_NAME := dwlabcmkapi
PYTHON ?= python3
BUILD_ARTIFACTS := dist
INSTALL_TARGET ?=

.PHONY: help build clean inspect install test

help:
	@echo "Targets for $(PACKAGE_NAME):"
	@echo "  make build        Build wheel and sdist artifacts into $(BUILD_ARTIFACTS)"
	@echo "  make clean        Remove local build and test artifacts"
	@echo "  make inspect      List generated distribution files"
	@echo "  make install      Pip install into INSTALL_TARGET or the active environment"
	@echo "  make test         Run the local pytest suite"

build:
	$(PYTHON) -m build --no-isolation

clean:
	rm -rf .pybuild .pytest_cache build dist *.egg-info src/*.egg-info tests/__pycache__ */__pycache__

inspect:
	@ls -1 "$(BUILD_ARTIFACTS)"/$(PACKAGE_NAME)-* 2>/dev/null || echo "No distribution artifacts built yet."

install:
	$(PYTHON) -m pip install $(if $(INSTALL_TARGET),--target "$(INSTALL_TARGET)",.) .

test:
	$(PYTHON) -m pytest
