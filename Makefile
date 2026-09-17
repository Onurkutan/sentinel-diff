.PHONY: all check test lint hygiene clean

all: check

check: lint test hygiene

lint:
	ruff check src/ tests/

test:
	pytest tests/ -q

hygiene:
	python scripts/check_repo_hygiene.py

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache
