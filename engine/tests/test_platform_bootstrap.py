"""V7 platform-parent/bootstrap protocol tests without native authorization."""

from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.resources
import importlib.util
import inspect
import os
import tempfile
import types
import unittest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_PATH = ROOT / "kernel/bin/awa-registration-bootstrap.py"
CHILD_PATH = ROOT / "kernel/bin/awa-registration-child.py"
ENTRYPOINT_PATH = ROOT / "kernel/bin/awa-registration-entrypoint.sh"
ADMIN_PATH = ROOT / "kernel/bin/awa-private-runtime-admin.py"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location(
        "awa_registration_bootstrap_test", BOOTSTRAP_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("bootstrap module unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_child():
    spec = importlib.util.spec_from_file_location(
        "awa_registration_child_test", CHILD_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("child module unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FdMappingTest(unittest.TestCase):
    def test_high_fd_plan_survives_all_source_target_collisions(self) -> None:
        bootstrap = _load_bootstrap()
        roles = tuple(bootstrap.FD_ASSIGNMENTS)
        targets = tuple(bootstrap.FD_ASSIGNMENTS.values())
        sources = {
            role: targets[(index + 1) % len(targets)]
            for index, role in enumerate(roles)
        }
        actions = bootstrap.plan_fd_remap(sources)
        target_by_role = {
            role: target
            for role, target in bootstrap.FD_ASSIGNMENTS.items()
        }
        high_sources = {
            action.target
            for action in actions
            if action.operation == "duplicate_high"
        }
        self.assertTrue(high_sources)
        self.assertTrue(
            all(fd >= bootstrap.MINIMUM_REMAP_FD for fd in high_sources)
        )
        final_actions = [
            action for action in actions if action.operation == "map_fixed"
        ]
        self.assertEqual(
            {action.role: action.target for action in final_actions},
            target_by_role,
        )
        self.assertTrue(
            all(action.source >= bootstrap.MINIMUM_REMAP_FD for action in final_actions)
        )

    def test_duplicate_source_is_refused_before_any_action(self) -> None:
        bootstrap = _load_bootstrap()
        with self.assertRaises(ValueError):
            bootstrap.plan_fd_remap(
                {
                    **{
                        role: 20 + index
                        for index, role in enumerate(
                            bootstrap.FD_ASSIGNMENTS
                        )
                    },
                    "runtime_manifest": 20,
                }
            )


class V8FdTopologyTest(unittest.TestCase):
    def test_v12_fixed_fd3_through_fd15_roles_are_exact(self) -> None:
        bootstrap = _load_bootstrap()
        self.assertEqual(
            bootstrap.FD_ASSIGNMENTS,
            {
                "control": 3,
                "runtime_manifest": 4,
                "import_manifest": 5,
                "owner_gate": 6,
                "runtime_current": 7,
                "launch_context": 8,
                "product_current": 9,
                "product_bundle_directory": 10,
                "bundle_manifest": 11,
                "bundle_projection": 12,
                "direct_receipt": 13,
                "host_authority": 14,
                "writer_capability": 15,
            },
        )
        self.assertEqual(
            set(bootstrap.FD_ASSIGNMENTS.values()), set(range(3, 16))
        )

    def test_v12_child_remeasures_all_authority_at_ready_and_go(self) -> None:
        source = CHILD_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        await_parent_go = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "await_parent_go"
        )
        verify_calls = sorted(
            (
                node
                for node in ast.walk(await_parent_go)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_verify_authority_fds"
            ),
            key=lambda node: (node.lineno, node.col_offset),
        )
        ready_send = next(
            node
            for node in ast.walk(await_parent_go)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "sendall"
            and any(
                isinstance(part, ast.Constant)
                and isinstance(part.value, str)
                and "READY " in part.value
                for argument in node.args
                for part in ast.walk(argument)
            )
        )
        go_receive = next(
            node
            for node in ast.walk(await_parent_go)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "recv"
        )
        self.assertGreaterEqual(
            len(verify_calls),
            2,
            "child must independently verify retained descriptors at READY and GO",
        )
        self.assertLess(verify_calls[0].lineno, ready_send.lineno)
        self.assertGreater(verify_calls[-1].lineno, go_receive.lineno)

    def _record(
        self,
        bootstrap,
        fd: int,
        role: str,
        *,
        directory: bool = False,
        logical_name: str | None = None,
        relative_path: str | None = None,
        owner_module: str | None = None,
    ):
        return bootstrap.DescriptorRecordV2(
            fd=str(fd),
            role=role,
            kind="DIRECTORY" if directory else "REGULAR",
            logical_name=None if directory else (logical_name or role),
            relative_path=relative_path or f"authority/{role.lower()}.json",
            owner_module=owner_module,
            mode="0755" if directory else "0444",
            size=None if directory else "1",
            sha256=None if directory else f"{fd:064x}",
            st_dev="1",
            st_ino=str(fd),
            st_nlink="1",
        )

    def test_launch_context_v2_covers_fixed_and_dynamic_descriptors(self) -> None:
        bootstrap = _load_bootstrap()
        records = (
            self._record(
                bootstrap,
                9,
                "PRODUCT_CURRENT",
                relative_path="/Library/Application Support/AWA/product/current.v1",
            ),
            self._record(
                bootstrap,
                10,
                "PRODUCT_BUNDLE_DIRECTORY",
                directory=True,
                relative_path="versions/1-" + "1" * 64,
            ),
            self._record(bootstrap, 11, "BUNDLE_MANIFEST"),
            self._record(bootstrap, 12, "BUNDLE_PROJECTION"),
            self._record(bootstrap, 13, "DIRECT_RECEIPT"),
            self._record(bootstrap, 14, "HOST_AUTHORITY"),
            self._record(bootstrap, 15, "WRITER_CAPABILITY"),
            self._record(
                bootstrap,
                16,
                "PACKAGE_INITIALIZER",
                logical_name="engine",
                relative_path="payload/engine/__init__.py",
                owner_module="engine",
            ),
        )
        context = bootstrap.LaunchContextV2.create(
            route="RECEIVER",
            nonce="a" * 64,
            expected_parent_pid="123",
            exact_head="b" * 40,
            runtime_manifest_sha256="c" * 64,
            runtime_current_digest="d" * 64,
            product_current_digest="e" * 64,
            bundle_digest="f" * 64,
            bundle_projection_hash="0" * 64,
            direct_receipt_digest="1" * 64,
            owner_gate_digest="2" * 64,
            import_manifest_hash="3" * 64,
            host_authority_digest="4" * 64,
            writer_capability_hash="5" * 64,
            descriptor_records=records,
        )
        self.assertEqual(context.descriptor_count, "8")
        self.assertEqual(
            bootstrap.LaunchContextV2.from_bytes(context.to_bytes()), context
        )
        changed = context.to_mapping()
        changed["descriptor_records"][1]["mode"] = "0700"
        with self.assertRaises(ValueError):
            bootstrap.LaunchContextV2.from_mapping(changed)

    def test_v2_remap_uses_collision_free_sources_above_dynamic_targets(self) -> None:
        bootstrap = _load_bootstrap()
        sources = {target: 24 - target for target in range(3, 17)}
        actions = bootstrap.plan_fd_remap_v2(sources)
        mapped = [item for item in actions if item.operation == "map_fixed"]
        self.assertEqual({item.target for item in mapped}, set(range(3, 17)))
        self.assertTrue(
            all(item.source >= 17 for item in mapped)
        )


class RetainedByteImporterTest(unittest.TestCase):
    def tearDown(self) -> None:
        for name in tuple(sys.modules):
            if name == "retainedpkg" or name.startswith("retainedpkg."):
                sys.modules.pop(name, None)

    def _record(self, child, kind, name, path, raw, owner=None):
        return child.RetainedImportRecord(
            kind=kind,
            logical_name=name,
            relative_path=path,
            owner_module=owner,
            mode="0444",
            sha256=hashlib.sha256(raw).hexdigest(),
            content=raw,
        )

    def test_relative_import_and_resource_use_retained_bytes_only(self) -> None:
        child = _load_child()
        records = (
            self._record(
                child,
                "PACKAGE_INITIALIZER",
                "retainedpkg",
                "payload/retainedpkg/__init__.py",
                b"",
            ),
            self._record(
                child,
                "MODULE",
                "retainedpkg.helper",
                "payload/retainedpkg/helper.py",
                b"VALUE = 41\n",
            ),
            self._record(
                child,
                "MODULE",
                "retainedpkg.receiver",
                "payload/retainedpkg/receiver.py",
                b"from .helper import VALUE\nRESULT = VALUE + 1\n",
            ),
            self._record(
                child,
                "RESOURCE",
                "schema.sql",
                "payload/retainedpkg/schema.sql",
                b"SELECT 1;\n",
                owner="retainedpkg.receiver",
            ),
        )
        importer = child.RetainedProductImporter(records)
        sys.meta_path.insert(0, importer)
        try:
            module = importlib.import_module("retainedpkg.receiver")
            self.assertEqual(module.RESULT, 42)
            self.assertTrue(module.__file__.startswith("awa-retained://"))
            resource = (
                importlib.resources.files(module)
                .joinpath("schema.sql")
                .read_bytes()
            )
            self.assertEqual(resource, b"SELECT 1;\n")
            with self.assertRaises(ModuleNotFoundError):
                importlib.import_module("retainedpkg.undeclared")
        finally:
            sys.meta_path.remove(importer)


class ParentChildBarrierTest(unittest.TestCase):
    def test_supervised_spawn_persists_every_barrier_before_success(self) -> None:
        bootstrap = _load_bootstrap()

        class Backend:
            parent_pid = 123
            parent_pidversion = "a" * 64
            boot_identity = "b" * 64

            def __init__(self) -> None:
                self.lines = [
                    b"READY " + b"c" * 64 + b"\n",
                    b"IMPORT_READY " + b"c" * 64 + b"\n",
                    b"TERMINAL " + b"c" * 64 + b" 0\n",
                ]
                self.sent = []
                self.terminated = False
                self.closed = False
                self.clock = 0

            def now_ns(self):
                self.clock += 1
                return str(self.clock)

            def spawn(self, plan, authority):
                self.plan = plan
                return bootstrap.SpawnedChild(
                    456,
                    "d" * 64,
                    authority.executable_vnode,
                    object(),
                )

            def receive_line(self, child, *, timeout_seconds):
                return self.lines.pop(0)

            def send_line(self, child, value):
                self.sent.append(value)

            def child_identity_is_continuous(self, child):
                return True

            def wait(self, child):
                return 0

            def terminate_and_reap(self, child):
                self.terminated = True

            def close(self, child):
                self.closed = True

        rechecks = []
        vnode = bootstrap.VnodeIdentity(1, 2, 0o100555, 0, 0, 1, 10)
        authority = bootstrap.RetainedLaunchAuthority(
            private_python="/Library/Application Support/AWA/runtime/versions/"
            + "1" * 64
            + "/Python.app/Contents/MacOS/Python",
            private_executable_sha256="2" * 64,
            runtime_manifest_sha256="1" * 64,
            version_lock_identity="3" * 64,
            authority_fds={
                role: 20 + index
                for index, role in enumerate(
                    role
                    for role in bootstrap.FD_ASSIGNMENTS
                    if role != "control"
                )
            },
            executable_vnode=vnode,
            reverify=lambda: rechecks.append("reverify"),
        )
        store = bootstrap.InMemoryIntentStore()
        backend = Backend()
        result = bootstrap.run_supervised_spawn(
            route="startup",
            nonce="c" * 64,
            authority=authority,
            store=store,
            backend=backend,
        )
        self.assertEqual(result, 0)
        self.assertEqual(store["c" * 64].phase, "TERMINAL")
        self.assertEqual(
            tuple(
                event
                for event in store.events
                if event.startswith(("create:", "transition:"))
            ),
            (
                "create:PREPARED",
                "transition:SPAWNED",
                "transition:READY",
                "transition:GO",
                "transition:PRODUCT",
                "transition:TERMINAL",
            ),
        )
        self.assertEqual(backend.sent, [b"GO " + b"c" * 64 + b"\n"])
        self.assertEqual(len(rechecks), 3)
        self.assertFalse(backend.terminated)
        self.assertTrue(backend.closed)

    def test_barrier_order_and_watchdog_are_closed(self) -> None:
        bootstrap = _load_bootstrap()
        barrier = bootstrap.ParentBarrier()
        with self.assertRaises(bootstrap.ProtocolRefusal):
            barrier.parent_send_go()
        barrier.child_ready()
        barrier.parent_reverify()
        barrier.parent_send_go()
        barrier.child_import_ready()
        barrier.child_product_imported()
        barrier.child_done()
        self.assertEqual(
            barrier.events,
            (
                "READY",
                "PARENT_REVERIFIED",
                "GO",
                "IMPORT_READY",
                "PRODUCT",
                "TERMINAL",
            ),
        )
        self.assertTrue(barrier.complete)

    def test_pre_go_timeout_and_parent_death_leave_no_product_import(self) -> None:
        bootstrap = _load_bootstrap()
        for event in ("WATCHDOG_TIMEOUT", "PARENT_DEAD", "CHANNEL_EOF"):
            with self.subTest(event=event):
                barrier = bootstrap.ParentBarrier()
                barrier.child_ready()
                barrier.child_abort(event)
                self.assertTrue(barrier.refused)
                self.assertNotIn("PRODUCT", barrier.events)
                with self.assertRaises(bootstrap.ProtocolRefusal):
                    barrier.child_product_imported()

    def test_child_source_has_no_product_import_before_go(self) -> None:
        source = CHILD_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_engine_imports = [
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
            and (
                getattr(node, "module", "") == "engine"
                or getattr(node, "module", "").startswith("engine.")
                or any(alias.name == "engine" or alias.name.startswith("engine.")
                       for alias in getattr(node, "names", ()))
            )
        ]
        self.assertEqual(top_level_engine_imports, [])
        self.assertIn("await_parent_go", source)
        self.assertIn("importlib.import_module", source)
        self.assertLess(source.index("await_parent_go("), source.index("importlib.import_module"))


class BootstrapMeasurementTest(unittest.TestCase):
    def test_fixed_launch_plan_contains_only_contract_literals(self) -> None:
        bootstrap = _load_bootstrap()
        plan = bootstrap.build_child_spawn_plan(
            private_python="/Library/Application Support/AWA/runtime/versions/"
            + "1" * 64
            + "/Python.app/Contents/MacOS/Python",
            route="startup",
            parent_pid=123,
            nonce="a" * 64,
        )
        self.assertEqual(
            plan.argv,
            (
                "/Library/Application Support/AWA/runtime/versions/"
                + "1" * 64
                + "/Python.app/Contents/MacOS/Python",
                "-I",
                "-S",
                "-B",
                "/Library/Application Support/AWA/bootstrap/v1/child.py",
                "--route",
                "startup",
                "--expected-parent-pid",
                "123",
                "--nonce",
                "a" * 64,
            ),
        )
        self.assertEqual(
            plan.environment,
            {
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin",
                "AWA_REGISTRATION_SPAWN_NONCE": "a" * 64,
            },
        )
        self.assertEqual(plan.fixed_fds, frozenset(range(3, 16)))

    def test_common_measurement_rejects_symlink_linkcount_mode_and_hash_drift(
        self,
    ) -> None:
        bootstrap = _load_bootstrap()
        with tempfile.TemporaryDirectory(prefix="awa-bootstrap-measurement.") as raw:
            root = Path(raw)
            files = {}
            for name in bootstrap.COMMON_MEASUREMENT_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode("utf-8"))
                path.chmod(0o444)
                files[name] = bootstrap.FileExpectation.from_path(path)
            bootstrap.verify_common_measurement(root, files)
            drift = root / next(iter(bootstrap.COMMON_MEASUREMENT_FILES))
            drift.chmod(0o644)
            with self.assertRaises(bootstrap.MeasurementRefusal):
                bootstrap.verify_common_measurement(root, files)

    def test_mapped_vnode_supplemental_checks_are_fail_closed(self) -> None:
        bootstrap = _load_bootstrap()
        expected = bootstrap.VnodeIdentity(
            device=1,
            inode=2,
            mode=0o100444,
            uid=0,
            gid=0,
            link_count=1,
            size=10,
        )
        bootstrap.verify_mapped_vnode(expected, expected)
        for field in (
            "device",
            "inode",
            "mode",
            "uid",
            "gid",
            "link_count",
            "size",
        ):
            with self.subTest(field=field):
                values = expected.__dict__.copy()
                values[field] += 1
                with self.assertRaises(bootstrap.MeasurementRefusal):
                    bootstrap.verify_mapped_vnode(
                        expected, bootstrap.VnodeIdentity(**values)
                    )


class EntrypointStaticTest(unittest.TestCase):
    def test_shell_entrypoint_is_pathless_and_has_no_dynamic_interpreter(self) -> None:
        source = ENTRYPOINT_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "/usr/bin/python3 -I -S -B",
            source,
        )
        self.assertIn(
            "/Library/Application Support/AWA/bootstrap/v1/bootstrap.py",
            source,
        )
        self.assertNotIn("AWA_REGISTRATION_INTERPRETER", source)
        self.assertNotIn("runtime-config.json", source)
        self.assertNotIn("/usr/local", source)
        self.assertNotIn("/opt/homebrew", source)

    def test_admin_and_bootstrap_are_stdlib_only(self) -> None:
        for path in (BOOTSTRAP_PATH, CHILD_PATH, ADMIN_PATH):
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
                imported = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported.update(alias.name.split(".")[0] for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported.add(node.module.split(".")[0])
                self.assertFalse(imported & {"requests", "cryptography", "pydantic"})


if __name__ == "__main__":
    unittest.main()
