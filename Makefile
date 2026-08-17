# AWA — Agent Worktree Automation (standalone system). Make targets: help-first, .PHONY.
.DEFAULT_GOAL := help
.PHONY: help install repair doctor check uninstall verify verify-install test trial version

help: ## Show available targets
	@echo "AWA — Agent Worktree Automation (standalone system: generic kernel + engine + dashboard)"
	@echo "  make install         - install AWA into your XDG dirs (idempotent)"
	@echo "  make repair          - force re-copy runtime + reconcile hook owner/mcp"
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

repair: ## Force re-copy the runtime and reconcile hook owner/mcp
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
	@set -e; direct_tmp=$$(mktemp -d); external_tmp=$$(mktemp -d); \
	  trap 'rm -rf "$$direct_tmp" "$$external_tmp"' EXIT; \
	  env -i PATH="$$PATH" TMPDIR=$$direct_tmp HOME=$$direct_tmp XDG_DATA_HOME=$$direct_tmp/.local/share XDG_CONFIG_HOME=$$direct_tmp/.config XDG_STATE_HOME=$$direct_tmp/.local/state ./install.sh >/dev/null; \
	  env -i PATH="$$PATH" TMPDIR=$$direct_tmp HOME=$$direct_tmp XDG_DATA_HOME=$$direct_tmp/.local/share XDG_CONFIG_HOME=$$direct_tmp/.config XDG_STATE_HOME=$$direct_tmp/.local/state ./install.sh >/dev/null; \
	  echo "  idempotent double-install OK"; \
	  env -i PATH="$$PATH" TMPDIR=$$direct_tmp HOME=$$direct_tmp XDG_DATA_HOME=$$direct_tmp/.local/share XDG_CONFIG_HOME=$$direct_tmp/.config XDG_STATE_HOME=$$direct_tmp/.local/state ./install.sh --doctor; \
	  version=$$(PYTHONPATH=. python3 -c 'import engine; print(engine.__version__)'); \
	  env -i PATH="$$PATH" TMPDIR=$$direct_tmp HOME=$$direct_tmp XDG_DATA_HOME=$$direct_tmp/.local/share XDG_CONFIG_HOME=$$direct_tmp/.config XDG_STATE_HOME=$$direct_tmp/.local/state \
	    PYTHONPATH=. python3 engine/tests/install_mcp_smoke.py \
	      $$direct_tmp/.local/share/awa/current/bin/awa-engine.sh $$version; \
	  echo "  installed MCP initialize/initialized/list/read/tools.list OK"; \
	  env -i PATH="$$PATH" TMPDIR=$$direct_tmp HOME=$$direct_tmp XDG_DATA_HOME=$$direct_tmp/.local/share XDG_CONFIG_HOME=$$direct_tmp/.config XDG_STATE_HOME=$$direct_tmp/.local/state ./install.sh --uninstall >/dev/null; \
	  hooks="$$external_tmp/selected-hooks/hooks.json"; \
	  mkdir -p "$$(dirname "$$hooks")"; \
	  printf '%s\n' '{"version":1,"hooks":{"beforeReadFile":[{"command":"/generic/foreign/sentinel.sh","type":"command","timeout":7}]}}' >"$$hooks"; \
	  snapshot() { python3 -c 'import glob,hashlib,json,os,stat,sys; p=sys.argv[1]; s=os.stat(p); hs=lambda q:hashlib.sha256(open(q,"rb").read()).hexdigest(); b=[(os.path.basename(q),stat.S_IMODE(os.stat(q).st_mode),hs(q)) for q in sorted(glob.glob(p+".bak-*"))]; print(json.dumps({"inode":s.st_ino,"mode":stat.S_IMODE(s.st_mode),"size":s.st_size,"mtime_ns":s.st_mtime_ns,"sha256":hs(p),"backups":b},sort_keys=True,separators=(",",":")))' "$$hooks"; }; \
	  external_before=$$(snapshot); \
	  env -i PATH="$$PATH" TMPDIR=$$external_tmp HOME=$$external_tmp XDG_DATA_HOME=$$external_tmp/.local/share XDG_CONFIG_HOME=$$external_tmp/.config XDG_STATE_HOME=$$external_tmp/.local/state AWA_HOOKS_JSON="$$hooks" AWA_HOOK_OWNER=external ./install.sh >/dev/null; \
	  env -i PATH="$$PATH" TMPDIR=$$external_tmp HOME=$$external_tmp XDG_DATA_HOME=$$external_tmp/.local/share XDG_CONFIG_HOME=$$external_tmp/.config XDG_STATE_HOME=$$external_tmp/.local/state AWA_HOOKS_JSON="$$hooks" ./install.sh >/dev/null; \
	  env -i PATH="$$PATH" TMPDIR=$$external_tmp HOME=$$external_tmp XDG_DATA_HOME=$$external_tmp/.local/share XDG_CONFIG_HOME=$$external_tmp/.config XDG_STATE_HOME=$$external_tmp/.local/state AWA_HOOKS_JSON="$$hooks" ./install.sh --repair >/dev/null; \
	  env -i PATH="$$PATH" TMPDIR=$$external_tmp HOME=$$external_tmp XDG_DATA_HOME=$$external_tmp/.local/share XDG_CONFIG_HOME=$$external_tmp/.config XDG_STATE_HOME=$$external_tmp/.local/state AWA_HOOKS_JSON="$$hooks" ./install.sh --doctor; \
	  env -i PATH="$$PATH" TMPDIR=$$external_tmp HOME=$$external_tmp XDG_DATA_HOME=$$external_tmp/.local/share XDG_CONFIG_HOME=$$external_tmp/.config XDG_STATE_HOME=$$external_tmp/.local/state AWA_HOOKS_JSON="$$hooks" ./install.sh --uninstall >/dev/null; \
	  test "$$(snapshot)" = "$$external_before"; \
	  echo "  external install/repair/doctor/uninstall zero hook-file access OK"; \
	  trap - EXIT; \
	  rm -rf "$$direct_tmp" "$$external_tmp"; \
	  echo "verify-install: OK"

version: ## Print the engine version
	@PYTHONPATH=. python3 -c "import engine; print(engine.__version__)"
