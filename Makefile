.PHONY: help install install-dev test lint format type-check clean docker-build docker-run docker-stop

help:
	@echo "Available commands:"
	@echo "  make install          - Install production dependencies"
	@echo "  make install-dev      - Install development dependencies"
	@echo "  make test             - Run tests with coverage"
	@echo "  make lint             - Run linting checks"
	@echo "  make format           - Format code with black"
	@echo "  make type-check       - Run type checking with mypy"
	@echo "  make clean            - Clean up cache and build files"
	@echo "  make docker-build     - Build Docker image"
	@echo "  make docker-run       - Run Docker container"
	@echo "  make docker-stop      - Stop Docker container"
	@echo "  make run              - Run the server locally"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --cov=mcp_ibkr_options --cov-report=term-missing

lint:
	ruff check src/ tests/

format:
	black src/ tests/

type-check:
	mypy src/

clean:
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache .coverage htmlcov/ .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build:
	docker build -t mcp-ibkr-options:local .

docker-run:
	docker-compose up -d

docker-stop:
	docker-compose down

run:
	python -m mcp_ibkr_options.server
