# AWA — Agent Worktree Automation (standalone system). Make targets: help-first, .PHONY.
.DEFAULT_GOAL := help
.PHONY: help install repair doctor check uninstall verify verify-install test trial version

help: ## Show available targets
	@echo "AWA — Agent Worktree Automation (standalone system: generic kernel + engine + dashboard)"
	@echo "  make install         - install AWA into your XDG dirs (idempotent)"
	@echo "  make repair          - force re-copy the runtime + re-wire hooks/mcp"
	@echo "  make doctor          - read-only health check of the install"
	@echo "  make check           - CI-safe static preflight (no writes to HOME)"
	@echo "  make uninstall       - remove the install (KEEP_STATE=1 preserves recovery state)"
	@echo "  make verify          - engine tests + contract freeze + zero-link + install --check"
	@echo "  make verify-install  - full install lifecycle in a throwaway HOME (headless/CI-safe)"
	@echo "  make test            - engine test suite (unittest; local-only, no network)"
	@echo "  make trial           - run the exact seven-step real-PM trial"
	@echo "  make version         - print the engine version"

install: ## Install AWA (idempotent)
	@./install.sh

repair: ## Force re-copy the runtime and re-wire hooks/mcp
	@./install.sh --repair

doctor: ## Read-only health check of the install
	@./install.sh --doctor

check: ## CI-safe static preflight (no writes to HOME)
	@./install.sh --check

uninstall: ## Remove the install (KEEP_STATE=1 to preserve recovery state)
	@./install.sh --uninstall $(if $(KEEP_STATE),--keep-state,)

test: ## Run the engine (kernel + engine core) test suite
	@bash engine/tests/run-tests.sh

trial: ## Run the exact real-PM facilitator workflow (TRIAL_ARGS=--auto for rehearsal)
	@PYTHONDONTWRITEBYTECODE=1 python3 -B consumer/trial_runner.py \
	  $(if $(TRIAL_FACILITATOR_LOG),--facilitator-log "$(TRIAL_FACILITATOR_LOG)",) $(TRIAL_ARGS)

verify: ## Full local verification: tests + freeze + zero-link + install --check
	@bash engine/tests/run-tests.sh
	@AWA_HOME=$(CURDIR) bash kernel/checks/awa-contract-freeze.sh
	@./install.sh --check
	@bash live-verify/verify-live-verify.sh
	@echo "verify: OK"

verify-install: ## Exercise the full install lifecycle in a throwaway HOME (never touches real ~)
	@set -e; tmp=$$(mktemp -d); \
	  trap 'rm -rf "$$tmp"' EXIT; \
	  env HOME=$$tmp XDG_DATA_HOME=$$tmp/.local/share XDG_CONFIG_HOME=$$tmp/.config XDG_STATE_HOME=$$tmp/.local/state ./install.sh >/dev/null; \
	  env HOME=$$tmp XDG_DATA_HOME=$$tmp/.local/share XDG_CONFIG_HOME=$$tmp/.config XDG_STATE_HOME=$$tmp/.local/state ./install.sh >/dev/null; \
	  echo "  idempotent double-install OK"; \
	  env HOME=$$tmp XDG_DATA_HOME=$$tmp/.local/share XDG_CONFIG_HOME=$$tmp/.config XDG_STATE_HOME=$$tmp/.local/state ./install.sh --doctor; \
	  version=$$(PYTHONPATH=. python3 -c 'import engine; print(engine.__version__)'); \
	  env HOME=$$tmp XDG_DATA_HOME=$$tmp/.local/share XDG_CONFIG_HOME=$$tmp/.config XDG_STATE_HOME=$$tmp/.local/state \
	    PYTHONPATH=. python3 engine/tests/install_mcp_smoke.py \
	      $$tmp/.local/share/awa/current/bin/awa-engine.sh $$version; \
	  echo "  installed MCP initialize/initialized/list/read/tools.list OK"; \
	  env HOME=$$tmp XDG_DATA_HOME=$$tmp/.local/share XDG_CONFIG_HOME=$$tmp/.config XDG_STATE_HOME=$$tmp/.local/state ./install.sh --uninstall >/dev/null; \
	  trap - EXIT; \
	  rm -rf $$tmp; \
	  echo "verify-install: OK"

version: ## Print the engine version
	@PYTHONPATH=. python3 -c "import engine; print(engine.__version__)"
