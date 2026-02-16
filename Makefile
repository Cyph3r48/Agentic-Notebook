.PHONY: test-backend test-backend-no-deps

test-backend:
	docker compose run --rm backend python -m pytest -q tests

test-backend-no-deps:
	docker compose run --rm --no-deps backend python -m pytest -q tests

