PYTHON ?= python

.PHONY: help install lint test up down logs migrate sim demo

help:
	@echo "install  - create venv and install the package with dev extras"
	@echo "lint     - ruff check"
	@echo "test     - pytest"
	@echo "up       - start postgres, rabbitmq, redis, api, dispatcher, consumer"
	@echo "down     - stop the stack and remove volumes"

install:
	$(PYTHON) -m venv .venv
	.venv/Scripts/python -m pip install --upgrade pip
	.venv/Scripts/python -m pip install -e ".[dev]"

lint:
	ruff check src tests mock_ros2

test:
	pytest -q

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f api dispatcher consumer

migrate:
	docker compose run --rm migrate

sim:
	python -m mock_ros2.robot_sim --count 2 --work-seconds 6 --failure-rate 0.2
