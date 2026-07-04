# AWA engine — make targets (help-first, .PHONY, self-documenting).
.DEFAULT_GOAL := help
.PHONY: help test verify version

help: ## Show available targets
	@echo "AWA engine"
	@echo "  make test     - run the engine test suite (unittest; local-only, no network)"
	@echo "  make verify   - run the suite (includes the zero-link preflight)"
	@echo "  make version  - print the engine version"

test: ## Run the engine (kernel + engine core) test suite
	@bash engine/tests/run-tests.sh

verify: ## Full local verification (the suite includes test_zero_link)
	@bash engine/tests/run-tests.sh
	@echo "verify: OK"

version: ## Print the engine version
	@PYTHONPATH=. python3 -c "import engine; print(engine.__version__)"
