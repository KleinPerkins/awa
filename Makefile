# AWA — Agent Worktree Automation (standalone system). Make targets: help-first, .PHONY.
.DEFAULT_GOAL := help
.PHONY: help install repair doctor check uninstall verify verify-docs verify-focused verify-pre-pr verify-performance verify-release verify-install verify-guard-installed-full private-runtime-check private-runtime-fixture private-runtime-qualification-inputs private-runtime-qualification-build test trial version
unexport VERIFY_BASE TESTS

help: ## Show available targets
	@echo "AWA — Agent Worktree Automation (standalone system: generic kernel + engine + dashboard)"
	@echo "  make install         - install AWA into your XDG dirs (idempotent)"
	@echo "  make repair          - force re-copy runtime + reconcile hook owner/mcp"
	@echo "  make doctor          - read-only health check of the install"
	@echo "  make check           - CI-safe static preflight (no writes to HOME)"
	@echo "  make uninstall       - remove the install (KEEP_STATE=1 preserves recovery state)"
	@echo "  make verify          - full gate (2 workers; AWA_TEST_JOBS=1 for serial)"
	@echo "  make verify-docs     - docs-only checks (VERIFY_BASE=<ref>; non-authoritative)"
	@echo "  make verify-focused  - explicit tests (TESTS='<selectors>'; non-authoritative)"
	@echo "  make verify-pre-pr   - complete authoritative local verification"
	@echo "  make verify-performance - full gate + explicit advisory process profile"
	@echo "  make verify-release  - selected release trial (TRIAL_ARGS='<args>')"
	@echo "  make verify-install  - full install lifecycle in a throwaway HOME (headless/CI-safe)"
	@echo "  make verify-guard-installed-full - complete serial installed-guard fallback"
	@echo "  make private-runtime-check - verify exact source lock/build tooling"
	@echo "  make private-runtime-fixture - two bounded synthetic builds (FIXTURE_SOURCE/FIXTURE_WORK)"
	@echo "  make test            - engine tests (2 workers; AWA_TEST_JOBS=1 for serial)"
	@echo "  make trial           - run the exact seven-step real-PM trial"
	@echo "  make version         - print the engine version"

install: ## Install AWA (idempotent)
	@bash ./install.sh

repair: ## Force re-copy the runtime and reconcile hook owner/mcp
	@bash ./install.sh --repair

doctor: ## Read-only health check of the install
	@bash ./install.sh --doctor

check: ## CI-safe static preflight (no writes to HOME)
	@bash ./install.sh --check

uninstall: ## Remove the install (KEEP_STATE=1 to preserve recovery state)
	@bash ./install.sh --uninstall $(if $(KEEP_STATE),--keep-state,)

test: ## Run the engine (kernel + engine core) test suite
	@bash engine/tests/run-tests.sh

trial: ## Run the exact real-PM facilitator workflow (TRIAL_ARGS=--auto for rehearsal)
	@PYTHONDONTWRITEBYTECODE=1 python3 -B consumer/trial_runner.py \
	  $(if $(TRIAL_FACILITATOR_LOG),--facilitator-log "$(TRIAL_FACILITATOR_LOG)",) $(TRIAL_ARGS)

verify: ## Full local verification: tests + freeze + zero-link + install --check
	@set -e; external_receipt="$${AWA_PERFORMANCE_RECEIPT:-}"; \
	  receipt="$$external_receipt"; \
	  if [ -z "$$receipt" ]; then receipt=$$(mktemp "$${TMPDIR:-/tmp}/awa-performance-receipt.XXXXXX"); fi; \
	  trap 'if [ -z "$$external_receipt" ]; then rm -f "$$receipt"; fi' EXIT; \
	  AWA_TEST_RECEIPT="$$receipt" AWA_TEST_LANE=pre-pr bash engine/tests/run-tests.sh; \
	  bash build/private-runtime/build.sh --check; \
	  bash ./install.sh --check; \
	  bash live-verify/verify-live-verify.sh; \
	  echo "verify: OK"; \
	  if [ "$${AWA_PERFORMANCE_WARNINGS_DISABLED:-0}" != "1" ]; then \
	    elapsed=$$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run"]["elapsed_ms"])' "$$receipt"); \
	    python3 -B -m engine.tests.performance_policy evaluate-lane --lane pre-pr --elapsed-ms "$$elapsed" --receipt "$$receipt"; \
	  fi

verify-docs: export AWA_VERIFY_BASE := $(value VERIFY_BASE)
verify-docs: ## Verify docs-only changes (non-authoritative for runtime)
	@set -e; manifest=$$(mktemp "$${TMPDIR:-/tmp}/awa-docs-manifest.XXXXXX"); \
	  trap 'rm -f "$$manifest"' EXIT; \
	  start=$$(python3 -c 'import time; print(time.monotonic_ns())'); \
	  PYTHONDONTWRITEBYTECODE=1 python3 -B -m engine.tests.verify_lane require-docs --base-env AWA_VERIFY_BASE >"$$manifest"; \
	  end=$$(python3 -c 'import time; print(time.monotonic_ns())'); \
	  elapsed=$$(((end-start)/1000000)); \
	  cat "$$manifest"; \
	  digest=$$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$$manifest"); \
	  echo "verify-docs: OK (NON-AUTHORITATIVE FOR RUNTIME)"; \
	  python3 -B -m engine.tests.performance_policy evaluate-lane --lane docs --elapsed-ms "$$elapsed" --inventory-sha256 "$$digest" --test-count 0 --load-note "$${AWA_TEST_LOAD_NOTE:-not_provided}"

verify-focused: export AWA_TEST_SELECTORS := $(value TESTS)
verify-focused: ## Run explicit tests (non-authoritative)
	@echo "verify-focused: NON-AUTHORITATIVE"
	@bash engine/tests/run-tests.sh --jobs 1 --selectors-env AWA_TEST_SELECTORS

verify-pre-pr: verify ## Run complete authoritative local verification

private-runtime-check: ## Verify accepted source-lock and deterministic tooling
	@bash build/private-runtime/build.sh --check

private-runtime-fixture: ## Build one bounded synthetic fixture twice
	@test -n "$(FIXTURE_SOURCE)" -a -n "$(FIXTURE_WORK)" || { \
	  echo "FIXTURE_SOURCE and FIXTURE_WORK are required" >&2; exit 2; }
	@bash build/private-runtime/build.sh --synthetic-fixture \
	  "$(FIXTURE_SOURCE)" "$(FIXTURE_WORK)"

private-runtime-qualification-inputs: ## Later-gated exact input collection
	@test -n "$(PRIVATE_RUNTIME_CACHE)" || { \
	  echo "PRIVATE_RUNTIME_CACHE is required" >&2; exit 2; }
	@bash build/private-runtime/build.sh --qualification-inputs \
	  "$(PRIVATE_RUNTIME_CACHE)"

private-runtime-qualification-build: ## Later-gated real two-root build
	@test -n "$(PRIVATE_RUNTIME_CACHE)" -a -n "$(PRIVATE_RUNTIME_WORK)" || { \
	  echo "PRIVATE_RUNTIME_CACHE and PRIVATE_RUNTIME_WORK are required" >&2; exit 2; }
	@bash build/private-runtime/build.sh --qualification-build \
	  "$(PRIVATE_RUNTIME_CACHE)" "$(PRIVATE_RUNTIME_WORK)"

verify-performance: ## Explicit expensive process profile + one authoritative verify
	@set -u; profile=$$(mktemp "$${TMPDIR:-/tmp}/awa-performance-profile.XXXXXX"); \
	  receipt=$$(mktemp "$${TMPDIR:-/tmp}/awa-performance-receipt.XXXXXX"); \
	  trap 'rm -f "$$profile" "$$receipt"' EXIT; \
	  first_rc=0; \
	  AWA_PERFORMANCE_WARNINGS_DISABLED=1 AWA_PERFORMANCE_RECEIPT="$$receipt" $(MAKE) verify || { verify_rc=$$?; if [ "$$first_rc" -eq 0 ]; then first_rc=$$verify_rc; fi; }; \
	  if [ "$$first_rc" -eq 0 ]; then \
	    python3 -B -m engine.tests.guard_boundary_profile --boundary source --count-git --json-out "$$profile" || first_rc=$$?; \
	  fi; \
	  if [ "$$first_rc" -eq 0 ]; then \
	    elapsed=$$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run"]["elapsed_ms"])' "$$receipt"); \
	    python3 -B -m engine.tests.performance_policy evaluate-lane --lane pre-pr --elapsed-ms "$$elapsed" --receipt "$$receipt" --process-profile "$$profile" || first_rc=$$?; \
	  fi; \
	  exit "$$first_rc"

verify-release: ## Run the selected release trial
	@$(MAKE) trial TRIAL_ARGS="$(TRIAL_ARGS)"

verify-guard-installed-full: ## Run the complete pre-layering installed-guard matrix
	@AWA_FULL_INSTALLED_GUARD_MATRIX=1 \
	  AWA_TEST_SELECTORS='engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity.test_primary_maintenance_command_corpus_engine_source_installed_parity engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity.test_primary_maintenance_state_corpus_engine_source_installed_parity engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity.test_primary_fetch_state_allow_corpus_engine_source_installed_parity engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity.test_m3_profile_manifest_matches_source_and_installed_permissions engine.tests.test_hook_owner_modes.TestHookOwnerParity.test_m3_profile_manifest_matches_owner_paths' \
	  bash engine/tests/run-tests.sh --jobs 1 --selectors-env AWA_TEST_SELECTORS
	@echo "verify-guard-installed-full: OK"

verify-install: verify-guard-installed-full ## Exercise the full install lifecycle in a throwaway HOME (never touches real ~)
	@set -e; direct_tmp=$$(mktemp -d); external_tmp=$$(mktemp -d); \
	  trap 'rm -rf "$$direct_tmp" "$$external_tmp"' EXIT; \
	  env -i PATH="$$PATH" TMPDIR=$$direct_tmp HOME=$$direct_tmp XDG_DATA_HOME=$$direct_tmp/.local/share XDG_CONFIG_HOME=$$direct_tmp/.config XDG_STATE_HOME=$$direct_tmp/.local/state bash ./install.sh >/dev/null; \
	  env -i PATH="$$PATH" TMPDIR=$$direct_tmp HOME=$$direct_tmp XDG_DATA_HOME=$$direct_tmp/.local/share XDG_CONFIG_HOME=$$direct_tmp/.config XDG_STATE_HOME=$$direct_tmp/.local/state bash ./install.sh >/dev/null; \
	  echo "  idempotent double-install OK"; \
	  env -i PATH="$$PATH" TMPDIR=$$direct_tmp HOME=$$direct_tmp XDG_DATA_HOME=$$direct_tmp/.local/share XDG_CONFIG_HOME=$$direct_tmp/.config XDG_STATE_HOME=$$direct_tmp/.local/state bash ./install.sh --doctor; \
	  version=$$(PYTHONPATH=. python3 -c 'import engine; print(engine.__version__)'); \
	  env -i PATH="$$PATH" TMPDIR=$$direct_tmp HOME=$$direct_tmp XDG_DATA_HOME=$$direct_tmp/.local/share XDG_CONFIG_HOME=$$direct_tmp/.config XDG_STATE_HOME=$$direct_tmp/.local/state \
	    PYTHONPATH=. python3 engine/tests/install_mcp_smoke.py \
	      $$direct_tmp/.local/share/awa/current/bin/awa-engine.sh $$version; \
	  echo "  installed MCP initialize/initialized/list/read/tools.list OK"; \
	  env -i PATH="$$PATH" TMPDIR=$$direct_tmp HOME=$$direct_tmp XDG_DATA_HOME=$$direct_tmp/.local/share XDG_CONFIG_HOME=$$direct_tmp/.config XDG_STATE_HOME=$$direct_tmp/.local/state bash ./install.sh --uninstall >/dev/null; \
	  hooks="$$external_tmp/selected-hooks/hooks.json"; \
	  mkdir -p "$$(dirname "$$hooks")"; \
	  printf '%s\n' '{"version":1,"hooks":{"beforeReadFile":[{"command":"/generic/foreign/sentinel.sh","type":"command","timeout":7}]}}' >"$$hooks"; \
	  snapshot() { python3 -c 'import glob,hashlib,json,os,stat,sys; p=sys.argv[1]; s=os.stat(p); hs=lambda q:hashlib.sha256(open(q,"rb").read()).hexdigest(); b=[(os.path.basename(q),stat.S_IMODE(os.stat(q).st_mode),hs(q)) for q in sorted(glob.glob(p+".bak-*"))]; print(json.dumps({"inode":s.st_ino,"mode":stat.S_IMODE(s.st_mode),"size":s.st_size,"mtime_ns":s.st_mtime_ns,"sha256":hs(p),"backups":b},sort_keys=True,separators=(",",":")))' "$$hooks"; }; \
	  external_before=$$(snapshot); \
	  env -i PATH="$$PATH" TMPDIR=$$external_tmp HOME=$$external_tmp XDG_DATA_HOME=$$external_tmp/.local/share XDG_CONFIG_HOME=$$external_tmp/.config XDG_STATE_HOME=$$external_tmp/.local/state AWA_HOOKS_JSON="$$hooks" AWA_HOOK_OWNER=external bash ./install.sh >/dev/null; \
	  env -i PATH="$$PATH" TMPDIR=$$external_tmp HOME=$$external_tmp XDG_DATA_HOME=$$external_tmp/.local/share XDG_CONFIG_HOME=$$external_tmp/.config XDG_STATE_HOME=$$external_tmp/.local/state AWA_HOOKS_JSON="$$hooks" bash ./install.sh >/dev/null; \
	  env -i PATH="$$PATH" TMPDIR=$$external_tmp HOME=$$external_tmp XDG_DATA_HOME=$$external_tmp/.local/share XDG_CONFIG_HOME=$$external_tmp/.config XDG_STATE_HOME=$$external_tmp/.local/state AWA_HOOKS_JSON="$$hooks" bash ./install.sh --repair >/dev/null; \
	  env -i PATH="$$PATH" TMPDIR=$$external_tmp HOME=$$external_tmp XDG_DATA_HOME=$$external_tmp/.local/share XDG_CONFIG_HOME=$$external_tmp/.config XDG_STATE_HOME=$$external_tmp/.local/state AWA_HOOKS_JSON="$$hooks" bash ./install.sh --doctor; \
	  env -i PATH="$$PATH" TMPDIR=$$external_tmp HOME=$$external_tmp XDG_DATA_HOME=$$external_tmp/.local/share XDG_CONFIG_HOME=$$external_tmp/.config XDG_STATE_HOME=$$external_tmp/.local/state AWA_HOOKS_JSON="$$hooks" bash ./install.sh --uninstall >/dev/null; \
	  test "$$(snapshot)" = "$$external_before"; \
	  echo "  external install/repair/doctor/uninstall zero hook-file access OK"; \
	  trap - EXIT; \
	  rm -rf "$$direct_tmp" "$$external_tmp"; \
	  echo "verify-install: OK"

version: ## Print the engine version
	@PYTHONPATH=. python3 -c "import engine; print(engine.__version__)"
