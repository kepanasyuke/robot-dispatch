# Thin wrapper around scripts/dev.py: the same tasks work with and without GNU make.
PYTHON ?= python
DEV = $(PYTHON) scripts/dev.py

.PHONY: help install lint format typecheck test check proto docs game-gif projects up down logs migrate sim

help:
	@$(DEV) help

install:
	@$(DEV) install

lint:
	@$(DEV) lint

format:
	@$(DEV) format

typecheck:
	@$(DEV) typecheck

test:
	@$(DEV) test

check:
	@$(DEV) check

proto:
	@$(DEV) proto

docs:
	@$(DEV) docs

game-gif:
	@$(DEV) game-gif

projects:
	@$(DEV) projects

up:
	@$(DEV) up

down:
	@$(DEV) down

logs:
	@$(DEV) logs

migrate:
	@$(DEV) migrate

sim:
	@$(DEV) sim
