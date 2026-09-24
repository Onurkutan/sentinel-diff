.PHONY: all check test lint hygiene clean

all: check

check: lint test hygiene

lint:
	python -m ruff check src/ tests/

test:
	python -m pytest tests/ -q

hygiene:
	python scripts/check_repo_hygiene.py

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache
