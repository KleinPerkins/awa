"""Synthetic offline first-prompt source tests; never native-host evidence."""
import fcntl
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'live-verify/codex-native-capture-v3'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


c = load('first_prompt_core', SOURCE/'capture_hook.py')
v = load('first_prompt_verifier', SOURCE/'verify_capture.py')
v.c = c


class Epoch:
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.awa-first-prompt-', dir=ROOT)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.fixture = self.root/'fixture'
        self.capture = self.root/'capture'
        for path in (self.fixture, self.fixture/'.codex', self.fixture/'.codex/hooks', self.capture):
            path.mkdir(mode=0o700)
        self.hook = self.fixture/'.codex/hooks/capture_hook.py'
        inputs, contents, catalog = v.source_inputs()
        self.put(self.hook, contents['capture_hook.py'])
        self.config = v.render_config(str(self.hook))
        self.put(self.fixture/'.codex/hooks.json', self.config)
        self.salt = b's'*32
        self.binding = hmac.new(self.salt, b'session\0primary', hashlib.sha256).digest()
        self.run = {'schema':'awa-codex-capture-run/v3','run_label':'C6','scenario_ids':['A02'],
                    'input_sha256':inputs,'hook_content_sha256':inputs['capture_hook.py'],
                    'rendered_config_sha256':c.digest(self.config),
                    'config_template_sha256':inputs['fixture-hooks.v3.json.in'],
                    'expected_event_counts':{'A02':[{name:int(name=='UserPromptSubmit') for name in c.EVENTS}]},
                    'control_event_names':{'A02':['UserPromptSubmit']},
                    'session_binding_sha256':c.digest(self.binding)}
        manifest = c.canonical(self.run)
        self.manifest_hash = c.digest(manifest)
        self.action_hash = c.digest(c.canonical(catalog['A02']))
        for name, raw in {'manifest.json':manifest,'salt.bin':self.salt,'session.bin':self.binding,
                          'labels.json':c.canonical({'session':{self.binding.hex():'S1'},'turn':{}}),
                          'capture.lock':b'','collector-contention.bin':b'0','ledger.ndjson':b''}.items():
            self.put(self.capture/name, raw)
        self.append({'kind':'pre','scenario_id':'A02','nonce':'1'*32,
                     'action_sha256':self.action_hash,'manifest_sha256':self.manifest_hash})
        return self

    def __exit__(self, *_args):
        self.temp.cleanup()

    def put(self, path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)

    def append(self, row):
        with (self.capture/'ledger.ndjson').open('ab') as handle:
            handle.write(c.canonical(row)+b'\n')

    def rows(self):
        return [json.loads(line) for line in (self.capture/'ledger.ndjson').read_bytes().splitlines()]

    def rewrite(self, rows):
        self.put(self.capture/'ledger.ndjson', b''.join(c.canonical(row)+b'\n' for row in rows))

    def invoke(self, session='primary', turn='synthetic-turn'):
        raw={'session_id':session,'turn_id':turn,'cwd':str(self.fixture),
             'hook_event_name':'UserPromptSubmit','prompt':'SYNTHETIC_OFFLINE_TEST_ONLY'}
        result=subprocess.run([sys.executable,'-I','-S','-B',str(self.hook)],input=c.canonical(raw),
                              cwd=self.fixture,capture_output=True,timeout=5)
        if (result.returncode,result.stdout,result.stderr)!=(0,b'{}\n',b''):
            raise AssertionError('SYNTHETIC_OBSERVER_RESPONSE_CHANGED')

    def seal(self, before=0, action=1, after=1, health='UNAVAILABLE'):
        for _ in range(before):self.invoke(turn='before')
        self.append({'kind':'phase','scenario_id':'A02','nonce':'1'*32,
                     'phase':'ACTION','session_label':'S1'})
        for _ in range(action):self.invoke(turn='first')
        self.append({'kind':'phase','scenario_id':'A02','nonce':'1'*32,
                     'phase':'AFTER','session_label':'S1'})
        for _ in range(after):self.invoke(turn='after')
        self.append({'kind':'post','scenario_id':'A02','nonce':'1'*32,
                     'action_sha256':self.action_hash,'manifest_sha256':self.manifest_hash,
                     'terminal':'COMPLETED','origin':'HOST','health':health,
                     'config_stability':'MATCH','children_clean':True,'process_exit_class':'ZERO',
                     'action_session_label':'S1',
                     'control_sequences':{'UserPromptSubmit':{'before':0,'after':before+action+after if after else 0}}})
        for name in ('salt.bin','session.bin','labels.json'):(self.capture/name).unlink()


class TestFirstPrompt(unittest.TestCase):
    def refused(self, epoch):
        with self.assertRaises(c.Invalid):v.verify(str(epoch.capture))
        self.assertFalse((epoch.capture/'export.json').exists())
        self.assertFalse((epoch.capture/'export.pending').exists())

    def test_foreign_session_is_rejected_before_labels_or_ledger(self):
        with Epoch() as e:
            before=[(e.capture/n).read_bytes() for n in ('labels.json','ledger.ndjson')]
            e.invoke(session='foreign')
            self.assertEqual(before,[(e.capture/n).read_bytes() for n in ('labels.json','ledger.ndjson')])
            e.invoke();self.assertEqual(e.rows()[-1]['event']['session_label'],'S1')

    def test_raw_binding_cannot_be_ascii_hex(self):
        with Epoch() as e:
            e.put(e.capture/'session.bin',e.binding.hex().encode())
            e.invoke();self.assertEqual(len(e.rows()),1)

    def test_binding_drift_and_extra_session_mapping_are_refused(self):
        for change in ('binding','mapping'):
            with self.subTest(change=change),Epoch() as e:
                if change=='binding':e.put(e.capture/'session.bin',b'x'*32)
                else:e.put(e.capture/'labels.json',c.canonical({'session':{e.binding.hex():'S1','0'*64:'S2'},'turn':{}}))
                e.invoke();self.assertEqual(len(e.rows()),1)

    def test_renderer_installs_only_one_pinned_prompt_definition(self):
        with Epoch() as e:
            config=json.loads(e.config);self.assertEqual(list(config['hooks']),['UserPromptSubmit'])
            group=config['hooks']['UserPromptSubmit'];self.assertEqual(len(group),1)
            handlers=group[0]['hooks'];self.assertEqual(len(handlers),1)
            self.assertEqual(handlers[0]['command'],'/usr/bin/python3 -I -S -B "'+str(e.hook)+'"')
            self.assertEqual(handlers[0]['timeout'],3)

    def test_manifest_cannot_enable_another_scenario_route_or_count(self):
        with Epoch() as e:
            variants=[('scenario_ids',['A03']),('control_event_names',{'A02':['SessionStart']})]
            for n in (0,2):variants.append(('expected_event_counts',{'A02':[{name:n if name=='UserPromptSubmit' else 0 for name in c.EVENTS}]}))
            for field,value in variants:
                changed=dict(e.run,**{field:value})
                with self.subTest(field=field,value=value),self.assertRaises(c.Invalid):c.manifest(c.canonical(changed))

    def test_exact_first_and_after_events_export_only_unproven_unknown(self):
        with Epoch() as e:
            e.seal();digest=v.verify(str(e.capture));raw=(e.capture/'export.json').read_bytes();export=json.loads(raw)
            self.assertEqual(digest,c.digest(raw));self.assertEqual(export['schema'],'awa-codex-capture-export/v3')
            self.assertEqual(export['session_scope'],'CONTROLLER_BOUND');self.assertEqual(export['collector_contention'],'NOT_RECORDED')
            row=export['scenarios'][0];self.assertEqual(row['completion_status'],'UNPROVEN')
            self.assertEqual(row['harness_health'],'UNKNOWN');self.assertEqual(row['positive_control_route_match'],'UNAVAILABLE')
            self.assertEqual(row['observed_event_counts']['UserPromptSubmit'],1)
            self.assertEqual([event['session_label'] for event in export['events']],['S1','S1'])
            self.assertNotIn(b'primary',raw);self.assertNotIn(e.binding.hex().encode(),raw)
            schema=json.loads((SOURCE/'capture-schema.v3.json').read_text())
            for key in ('completion_status','harness_health','positive_control_route_match'):
                self.assertEqual(schema['$defs']['scenario']['properties'][key]['const'],row[key])
            self.assertEqual(schema['properties']['events']['minItems'],2)
            self.assertEqual(schema['properties']['events']['maxItems'],2)

    def test_first_prompt_can_never_assert_same_route_health(self):
        with Epoch() as e:e.seal(health='SAME_ROUTE');self.refused(e)

    def test_every_before_action_after_count_mismatch_is_refused(self):
        for shape in ({'before':1},{'action':0},{'action':2},{'after':0},{'after':2}):
            with self.subTest(shape=shape),Epoch() as e:e.seal(**shape);self.refused(e)

    def test_before_sequence_must_be_zero_and_after_sequence_exact(self):
        for name,value in (('before',1),('after',1),('after',0)):
            with self.subTest(name=name,value=value),Epoch() as e:
                e.seal();rows=e.rows();rows[-1]['control_sequences']['UserPromptSubmit'][name]=value;e.rewrite(rows);self.refused(e)

    def test_foreign_session_in_tampered_ledger_is_refused(self):
        with Epoch() as e:
            e.seal();rows=e.rows();next(r['event'] for r in rows if r['kind']=='event')['session_label']='S2';e.rewrite(rows);self.refused(e)

    def test_after_root_and_source_are_checked_even_without_healthy_claim(self):
        for name,value in (('root_label','SUBDIR'),('source','UNKNOWN')):
            with self.subTest(name=name),Epoch() as e:
                e.seal();rows=e.rows();next(r['event'] for r in rows if r['kind']=='event' and r['phase']=='AFTER')[name]=value;e.rewrite(rows);self.refused(e)

    def test_binding_ephemera_must_be_absent_for_offline_export(self):
        with Epoch() as e:e.seal();e.put(e.capture/'session.bin',e.binding);self.refused(e)

    def test_contention_flag_must_remain_through_verification(self):
        with Epoch() as e:e.seal();(e.capture/'collector-contention.bin').unlink();self.refused(e)

    def test_contended_callback_invalidates_an_otherwise_exact_epoch(self):
        with Epoch() as e:
            fd=os.open(e.capture/'capture.lock',os.O_RDWR)
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);e.invoke();self.assertEqual((e.capture/'collector-contention.bin').read_bytes(),b'1')
            finally:os.close(fd)
            e.seal();self.refused(e)

    def test_contention_during_verification_prevents_publication(self):
        with Epoch() as e:
            e.seal();original=c.read_rows
            def rows_then_contend(fd):
                rows=original(fd);(e.capture/'collector-contention.bin').write_bytes(b'1');return rows
            with mock.patch.object(c,'read_rows',side_effect=rows_then_contend):self.refused(e)

    def test_local_tool_definitions_remain_inert(self):
        _inputs,_contents,catalog=v.source_inputs()
        self.assertEqual([name for name,row in catalog.items() if row['executable']],['A02'])
        self.assertFalse(catalog['A04']['executable']);self.assertFalse(catalog['A05']['executable'])


if __name__=='__main__':unittest.main()
