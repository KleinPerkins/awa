"""Synthetic offline capture tests; these are never native-host evidence."""
import copy
import fcntl
import os
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'live-verify/codex-native-capture-v2'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


c = load('capture_binding_core', SOURCE / 'capture_hook.py')
v = load('capture_binding_verifier', SOURCE / 'verify_capture.py')
v.c = c


class TestSessionBinding(unittest.TestCase):
    def setUp(self):
        self.salt = b's' * 32
        self.binding = hmac.new(self.salt, b'session\0primary', hashlib.sha256).digest()
        self.labels = {'session': {self.binding.hex(): 'S1'}, 'turn': {}}

    def test_v1_admits_second_session_but_v2_rejects_it_without_label_allocation(self):
        old = load('unbound_capture_core', ROOT / 'live-verify/codex-native-capture-v1/capture_hook.py')
        labels = copy.deepcopy(self.labels)
        self.assertEqual(old.equality(labels, self.salt, 'session', 'secondary'), 'S2')
        before = copy.deepcopy(self.labels)
        with self.assertRaises(c.Invalid):
            c.bound_session({'session_id': 'secondary'}, self.labels, self.salt, self.binding)
        self.assertEqual(self.labels, before)

    def test_primary_is_bound_and_missing_or_malformed_session_is_rejected(self):
        self.assertEqual(c.bound_session({'session_id': 'primary'}, self.labels, self.salt, self.binding), 'S1')
        for raw in ({}, {'session_id': ''}, {'session_id': None}, {'session_id': 1}):
            with self.subTest(raw=raw), self.assertRaises(c.Invalid):
                c.bound_session(raw, self.labels, self.salt, self.binding)

    def test_mutated_mapping_cannot_rebind_primary(self):
        for mapping in ({}, {self.binding.hex(): 'S2'}, {self.binding.hex(): 'S1', '0'*64: 'S2'}):
            with self.subTest(mapping=mapping), self.assertRaises(c.Invalid):
                c.bound_session({'session_id': 'primary'}, {'session': mapping}, self.salt, self.binding)


class TestObserverAndVerifier(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.awa-bound-capture-', dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.operation = Path(self.temp.name).resolve()
        self.operation.chmod(0o700)
        self.fixture = self.operation / 'fixture'
        self.capture = self.operation / 'capture'
        for d in (self.fixture, self.fixture/'.codex', self.fixture/'.codex/hooks', self.capture):
            d.mkdir(mode=0o700)
        self.hook = self.fixture / '.codex/hooks/capture_hook.py'
        self.put(self.hook, (SOURCE/'capture_hook.py').read_bytes())
        inputs, _contents, catalog = v.source_inputs()
        config = v.render_config(str(self.hook))
        self.put(self.fixture/'.codex/hooks.json', config)
        self.salt = b's' * 32
        self.binding = hmac.new(self.salt, b'session\0primary', hashlib.sha256).digest()
        counts = dict.fromkeys(c.EVENTS, 0); counts['UserPromptSubmit'] = 1
        self.run = {'schema': 'awa-codex-capture-run/v2', 'run_label': 'C4', 'scenario_ids': ['A03'],
                    'input_sha256': inputs, 'hook_content_sha256': inputs['capture_hook.py'],
                    'rendered_config_sha256': c.digest(config),
                    'config_template_sha256': inputs['fixture-hooks.v2.json.in'],
                    'expected_event_counts': {'A03': [counts]}, 'control_event_names': {'A03': ['UserPromptSubmit']},
                    'session_binding_sha256': c.digest(self.binding)}
        manifest = c.canonical(self.run)
        self.manifest_hash = c.digest(manifest)
        self.action_hash = c.digest(c.canonical(catalog['A03']))
        for name, raw in {'manifest.json':manifest, 'salt.bin':self.salt, 'session.bin':self.binding,
                          'labels.json':c.canonical({'session':{self.binding.hex():'S1'},'turn':{}}),
                          'capture.lock':b'', 'collector-contention.bin':b'0', 'ledger.ndjson':b''}.items():
            self.put(self.capture/name, raw)
        self.append({'kind':'pre','scenario_id':'A03','nonce':'1'*32,'action_sha256':self.action_hash,
                     'manifest_sha256':self.manifest_hash})

    def put(self, path, raw):
        path.write_bytes(raw); path.chmod(0o600)

    def append(self, row):
        with (self.capture/'ledger.ndjson').open('ab') as f:
            f.write(c.canonical(row)+b'\n')

    def invoke(self, session='primary', turn='turn'):
        raw = {'session_id':session,'turn_id':turn,'cwd':str(self.fixture),'hook_event_name':'UserPromptSubmit',
               'prompt':'SYNTHETIC_OFFLINE_TEST_ONLY'}
        r = subprocess.run([sys.executable,'-I','-S','-B',str(self.hook)], input=c.canonical(raw),
                           cwd=self.fixture, capture_output=True, timeout=5)
        self.assertEqual((r.returncode,r.stdout,r.stderr), (0,b'{}\n',b''))

    def rows(self):
        return [json.loads(line) for line in (self.capture/'ledger.ndjson').read_bytes().splitlines()]

    def seal(self, duplicate_before=False, health='SAME_ROUTE'):
        self.invoke(turn='before')
        if duplicate_before:self.invoke(turn='before')
        self.append({'kind':'phase','scenario_id':'A03','nonce':'1'*32,'phase':'ACTION','session_label':'S1'})
        self.invoke(turn='action')
        self.append({'kind':'phase','scenario_id':'A03','nonce':'1'*32,'phase':'AFTER','session_label':'S1'})
        self.invoke(turn='after')
        n=4 if duplicate_before else 3
        self.append({'kind':'post','scenario_id':'A03','nonce':'1'*32,'action_sha256':self.action_hash,
                     'manifest_sha256':self.manifest_hash,'terminal':'COMPLETED','origin':'HOST','health':health,
                     'config_stability':'MATCH','children_clean':True,'process_exit_class':'ZERO',
                     'action_session_label':'S1','control_sequences':{'UserPromptSubmit':{'before':1,'after':n}}})
        for name in ('salt.bin','session.bin','labels.json'):(self.capture/name).unlink()

    def test_manifest_cannot_widen_counts_routes_or_selected_scenario(self):
        for field, value in (("scenario_ids", ["A01"]),
                             ("control_event_names", {"A03": ["SessionStart"]}),
                             ("expected_event_counts", {"A03": [dict.fromkeys(c.EVENTS, 0)]})):
            changed = dict(self.run, **{field: value})
            with self.subTest(field=field), self.assertRaises(c.Invalid):
                c.manifest(c.canonical(changed))

    def test_foreign_native_input_does_not_write_labels_or_ledger(self):
        before = [(self.capture/n).read_bytes() for n in ('ledger.ndjson','labels.json')]
        self.invoke('secondary')
        self.assertEqual(before, [(self.capture/n).read_bytes() for n in ('ledger.ndjson','labels.json')])
        self.invoke()
        self.assertEqual(self.rows()[-1]['event']['session_label'], 'S1')

    def test_ascii_hex_binding_is_not_accepted_as_raw_digest(self):
        wrong_encoding = self.binding.hex().encode('ascii')
        self.assertEqual(len(wrong_encoding), 64)
        self.put(self.capture/'session.bin', wrong_encoding)
        self.invoke()
        self.assertEqual(len(self.rows()), 1)

    def test_binding_file_drift_is_fail_open_without_capturing(self):
        self.put(self.capture/'session.bin', b'x'*32)
        self.invoke()
        self.assertEqual(len(self.rows()), 1)

    def test_three_primary_controls_verify_and_export_explicit_scope(self):
        self.seal()
        digest = v.verify(str(self.capture))
        raw = (self.capture/'export.json').read_bytes(); export = json.loads(raw)
        self.assertEqual(digest,c.digest(raw))
        self.assertEqual(export['session_scope'],'CONTROLLER_BOUND')
        self.assertEqual(export['collector_contention'],'NOT_RECORDED')
        self.assertEqual(export['scenarios'][0]['completion_status'],'OBSERVED')
        self.assertEqual([e['session_label'] for e in export['events']],['S1']*3)
        self.assertNotIn(b'primary',raw); self.assertNotIn(self.binding.hex().encode(),raw)

    def test_duplicate_primary_callback_still_fails_control(self):
        self.seal(duplicate_before=True)
        with self.assertRaises(c.Invalid):v.verify(str(self.capture))
        self.assertFalse((self.capture/'export.json').exists())

    def test_duplicate_primary_callback_unavailable_health_still_fails_control(self):
        self.seal(duplicate_before=True, health='UNAVAILABLE')
        with self.assertRaises(c.Invalid):v.verify(str(self.capture))
        self.assertFalse((self.capture/'export.json').exists())

    def test_exact_controls_unavailable_health_remain_unproven(self):
        self.seal(health='UNAVAILABLE')
        v.verify(str(self.capture))
        row = json.loads((self.capture/'export.json').read_bytes())['scenarios'][0]
        self.assertEqual(row['completion_status'], 'UNPROVEN')
        self.assertEqual(row['harness_health'], 'UNKNOWN')

    def test_contended_callback_leaves_sticky_evidence_and_cannot_export(self):
        fd = os.open(self.capture/'capture.lock', os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.invoke()
            self.assertEqual((self.capture/'collector-contention.bin').read_bytes(), b'1')
        finally:
            os.close(fd)
        # Otherwise exact controls cannot hide the earlier dropped invocation.
        self.seal()
        self.assertEqual((self.capture/'collector-contention.bin').read_bytes(), b'1')
        with self.assertRaises(c.Invalid):v.verify(str(self.capture))
        self.assertFalse((self.capture/'export.json').exists())

    def test_contention_evidence_must_remain_until_export(self):
        self.seal()
        (self.capture/'collector-contention.bin').unlink()
        with self.assertRaises(c.Invalid):v.verify(str(self.capture))

    def test_contention_recorded_during_verification_refuses_publication(self):
        self.seal()
        original = c.read_rows
        def rows_then_contend(fd):
            rows = original(fd)
            (self.capture/'collector-contention.bin').write_bytes(b'1')
            return rows
        with mock.patch.object(c, 'read_rows', side_effect=rows_then_contend):
            with self.assertRaises(c.Invalid):v.verify(str(self.capture))
        self.assertFalse((self.capture/'export.json').exists())
        self.assertFalse((self.capture/'export.pending').exists())

    def test_binding_ephemera_must_be_removed_before_export(self):
        self.seal(); self.put(self.capture/'session.bin',self.binding)
        with self.assertRaises(c.Invalid):v.verify(str(self.capture))

    def test_verifier_rejects_foreign_session_label_even_in_tampered_ledger(self):
        self.seal()
        rows = self.rows(); rows[1]['event']['session_label']='S2'
        self.put(self.capture/'ledger.ndjson', b''.join(c.canonical(r)+b'\n' for r in rows))
        with self.assertRaises(c.Invalid):v.verify(str(self.capture))


if __name__ == '__main__':
    unittest.main()
