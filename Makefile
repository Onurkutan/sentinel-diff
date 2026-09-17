.PHONY: all test check lint clean

all: check test

test:
	pytest tests/ -v

check:
	python scripts/check_repo_hygiene.py

lint:
	ruff check .

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache
