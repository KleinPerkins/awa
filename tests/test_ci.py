"""Adversarial CI controls; only local fixture inputs, no credentials or API calls."""
import copy, importlib.util, io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('awa_ci',ROOT/'scripts/verify.py');ci=importlib.util.module_from_spec(spec);spec.loader.exec_module(ci)
ENV=dict(GITHUB_REPOSITORY='KleinPerkins/awa',GITHUB_REPOSITORY_ID='1289571438',GITHUB_EVENT_NAME='pull_request',GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_RUN_ID='100',GITHUB_RUN_ATTEMPT='2',GITHUB_REF='refs/pull/12/merge',CI_HEAD_SHA='c'*40,CI_BASE_SHA='d'*40,GITHUB_WORKFLOW_REF='KleinPerkins/awa/.github/workflows/ci.yml@refs/pull/12/merge',GITHUB_WORKFLOW='CI')
def evidence():
    c,m,h=ci.policy()
    return {s:{'result':'success','outputs':{'receipt':json.dumps({'schema':'awa-ci-shard/v1','shard':s,'identity':ci.identity(ENV),'result':'success','measurement':{'commands':[ci.COMMANDS[s]],'case_count':2,'case_ids_sha256':'a'*64,'skips':[],'logs_sha256':'b'*64,'contract_sha256':h,'host':ci.HOSTS[s],'architecture':'fixture'}})}} for s in ci.SHARDS}
class AggregateTests(unittest.TestCase):
    def test_all_exact_lanes_required(self):
        ci.validate_aggregate(evidence(),ci.identity(ENV))
        for shard in ci.SHARDS:
            for status in ('failure','skipped','cancelled','neutral','timed_out',None):
                n=evidence();n[shard]['result']=status
                with self.subTest(shard=shard,status=status),self.assertRaises(ci.ContractError):ci.validate_aggregate(n,ci.identity(ENV))
            n=evidence();del n[shard]
            with self.assertRaises(ci.ContractError):ci.validate_aggregate(n,ci.identity(ENV))
    def test_missing_extra_malformed_and_duplicate_receipts_refuse(self):
        for raw in ('null','[]','{}','bad','{"schema":1,"schema":2}'):
            n=evidence();n['dashboard']['outputs']['receipt']=raw
            with self.assertRaises((ci.ContractError,ValueError)):ci.validate_aggregate(n,ci.identity(ENV))
        n=evidence();n['extra']=n['dashboard']
        with self.assertRaises(ci.ContractError):ci.validate_aggregate(n,ci.identity(ENV))
        n=evidence();n['dashboard']=n['source-native']
        with self.assertRaises(ci.ContractError):ci.validate_aggregate(n,ci.identity(ENV))
    def test_stale_run_tuple_commands_coverage_and_native_host_refuse(self):
        for key in ci.IDENTITY_KEYS:
            n=evidence();v=json.loads(n['source-native']['outputs']['receipt']);v['identity'][key]+='stale';n['source-native']['outputs']['receipt']=json.dumps(v)
            with self.subTest(identity=key),self.assertRaises(ci.ContractError):ci.validate_aggregate(n,ci.identity(ENV))
        mutations=[lambda v:v['measurement'].update(case_count=0),lambda v:v['measurement'].update(host='Linux'),lambda v:v['measurement'].update(commands=[]),lambda v:v['measurement'].update(contract_sha256='0'*64),lambda v:v['measurement'].update(skips=[{'case':'test','reason':'M1 supports macOS only'}])]
        for mutate in mutations:
            n=evidence();v=json.loads(n['source-native']['outputs']['receipt']);mutate(v);n['source-native']['outputs']['receipt']=json.dumps(v)
            with self.assertRaises(ci.ContractError):ci.validate_aggregate(n,ci.identity(ENV))
    def test_wrong_repository_event_workflow_and_ref_refuse(self):
        for key,value in [('GITHUB_REPOSITORY','KleinPerkins/dev'),('GITHUB_REPOSITORY_ID','1459458379'),('GITHUB_EVENT_NAME','pull_request_target'),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_REF','refs/heads/main'),('GITHUB_WORKFLOW_REF','wrong'),('GITHUB_RUN_ID','0')]:
            with self.subTest(key=key),self.assertRaises(ci.ContractError):ci.identity(dict(ENV,**{key:value}))
    def test_native_chflags_and_stock_sqlite_coverage_cannot_skip(self):
        for reason in ('meaningful only where chflags exists to shadow away','ADR 0025 requires stock SQLite >=3.51.3'):
            n=evidence();v=json.loads(n['source-native']['outputs']['receipt']);v['measurement']['skips']=[{'case':'native-fixture','reason':reason}];n['source-native']['outputs']['receipt']=json.dumps(v)
            with self.assertRaises(ci.ContractError):ci.validate_aggregate(n,ci.identity(ENV))
    def test_native_unknown_skip_ids_fail_regardless_of_reason_and_known_offswitch_passes(self):
        c,_,_=ci.policy()
        for case in ('engine.tests.test_registration_clock.ClockTests.test_required','native-fixture'):
            for reason in ('fixture unavailable','not supported here','macOS requirement'):
                n=evidence();v=json.loads(n['source-native']['outputs']['receipt']);v['measurement']['skips']=[{'case':case,'reason':reason}];n['source-native']['outputs']['receipt']=json.dumps(v)
                with self.subTest(case=case,reason=reason),self.assertRaises(ci.ContractError):ci.validate_aggregate(n,ci.identity(ENV))
        allowed=[{'case':case,'reason':'router off-switch'} for case in c['native_allowed_skip_ids']]
        ci.validate_native_skips(allowed,c)
        n=evidence();v=json.loads(n['source-native']['outputs']['receipt']);v['measurement'].update(case_count=16,skips=allowed);n['source-native']['outputs']['receipt']=json.dumps(v)
        ci.validate_aggregate(n,ci.identity(ENV))
        with self.assertRaises(ci.ContractError):ci.validate_native_skips(allowed+[{'case':'unexpected','reason':'router off-switch'}],c)
    def test_main_identity_is_distinct_from_pull_request(self):
        env=dict(ENV,GITHUB_EVENT_NAME='push',GITHUB_REF='refs/heads/main',CI_HEAD_SHA='',CI_BASE_SHA='',GITHUB_WORKFLOW_REF='KleinPerkins/awa/.github/workflows/ci.yml@refs/heads/main')
        current=ci.identity(env)
        with self.assertRaises(ci.ContractError):ci.validate_aggregate(evidence(),current)
class IsolationTests(unittest.TestCase):
    def test_bounded_failure_timeout_output_bound_and_environment(self):
        with self.assertRaises(ci.ContractError):ci.bounded([sys.executable,'-c','raise SystemExit(9)'],2)
        with self.assertRaises(ci.ContractError):ci.bounded([sys.executable,'-c','import time;time.sleep(5)'],.05)
        with patch.object(ci,'MAX_OUTPUT',32),self.assertRaises(ci.ContractError):ci.bounded([sys.executable,'-c','print("a"*40)'],2)
        with patch.dict(os.environ,GH_TOKEN='fixture',GITHUB_TOKEN='fixture',CI_READ_TOKEN='metadata-only-fixture',AWA_FULL_INSTALLED_GUARD_MATRIX='1',PYTHONPATH='foreign'):
            raw=ci.bounded([sys.executable,'-I','-c','import os,json;print(json.dumps({k:os.environ.get(k) for k in ["GH_TOKEN","GITHUB_TOKEN","CI_READ_TOKEN","AWA_FULL_INSTALLED_GUARD_MATRIX","PYTHONPATH","HOME"]}))'],2,overrides={'HOME':'/fixture-only'})
        self.assertEqual(json.loads(raw),dict(GH_TOKEN=None,GITHUB_TOKEN=None,CI_READ_TOKEN=None,AWA_FULL_INSTALLED_GUARD_MATRIX=None,PYTHONPATH=None,HOME='/fixture-only'))
    def test_private_fixture_base_has_secure_ancestry_and_darwin_uses_os_temp(self):
        base=ci.private_fixture_base();self.assertTrue(base.is_dir())
        if ci.platform.system()=='Darwin':self.assertNotIn('/Users/',str(base))
        with tempfile.TemporaryDirectory() as raw:
            parent=Path(raw);parent.chmod(0o777)
            with patch.object(ci.platform,'system',return_value='Darwin'),patch.object(ci.subprocess,'check_output',return_value=str(parent)):
                with self.assertRaises(ci.ContractError):ci.private_fixture_base()
    def test_real_multiline_unittest_labels_produce_complete_case_evidence(self):
        output=ci.bounded([sys.executable,'-B','-m','unittest','-v',
            'engine.tests.test_consumer_golden.TestGoldenSetShape'],20)
        with patch.object(ci,'bounded',return_value=output),patch('sys.stdout',new=io.StringIO()):
            measurement=ci.measured('dashboard',allow_cross_host=True)
        self.assertEqual(measurement['case_count'],7)
        self.assertEqual(measurement['skips'],[])
        damaged=b'\n'.join(line for line in output.split(b'\n') if not line.startswith(b'test_count_is_25_to_30 ('))
        with patch.object(ci,'bounded',return_value=damaged),patch('sys.stdout',new=io.StringIO()),self.assertRaises(ci.ContractError):
            ci.measured('dashboard',allow_cross_host=True)
    def test_native_full_corpus_uses_supported_serial_override_only(self):
        class StopBeforeCorpus(Exception):pass
        seen={}
        def capture(_argv,_timeout,**kwargs):
            seen.update(kwargs['overrides']);raise StopBeforeCorpus()
        with tempfile.TemporaryDirectory() as raw:
            for shard in ('source-native','source-portable'):
                seen.clear()
                with patch.object(ci,'private_fixture_base',return_value=Path(raw).resolve()),patch.object(ci.sqlite3,'sqlite_version_info',(3,51,3)),patch.object(ci.shutil,'which',return_value='/fixture/chflags'),patch.object(ci.importlib.util,'find_spec',return_value=None),patch.object(ci,'bounded',side_effect=capture),patch.dict(os.environ,AWA_TEST_JOBS='8'),self.assertRaises(StopBeforeCorpus):
                    ci.measured(shard,allow_cross_host=True)
                self.assertIn('AWA_PERFORMANCE_RECEIPT',seen)
                self.assertEqual(seen.get('AWA_TEST_JOBS'),'1' if shard=='source-native' else None)
        self.assertEqual(ci.policy()[0]['runtime_requirements']['native_test_jobs'],1)
    def test_unknown_router_binding_is_hard_failure(self):
        self.assertEqual(ci.router_binding()['repository_id'],1294651532)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'.github').mkdir();binding=json.loads((ROOT/'.github/router-ci-source.json').read_bytes());binding.update(enabled=False)
            (root/'.github/router-ci-source.json').write_text(json.dumps(binding))
            with self.assertRaisesRegex(ci.ContractError,'prerequisite unavailable'):ci.router_binding(root)
            binding.update(enabled=True,public_source=True,revision='f44dbadd')
            (root/'.github/router-ci-source.json').write_text(json.dumps(binding))
            with self.assertRaises(ci.ContractError):ci.router_binding(root)
    def test_router_binding_requires_immutable_id_and_consistent_provenance(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);(root/'.github').mkdir()
            binding=json.loads((ROOT/'.github/router-ci-source.json').read_bytes())
            provenance=json.loads((ROOT/'.github/ci-adapter-provenance.json').read_bytes())
            def write(b,p):
                (root/'.github/router-ci-source.json').write_text(json.dumps(b))
                (root/'.github/ci-adapter-provenance.json').write_text(json.dumps(p))
            write(binding,provenance)
            current=ci.router_binding(root)
            self.assertEqual(current['reviewed_head'],'9a9af7f2fb72d600a6dc01a7f99dfa9d2c822668')
            self.assertEqual(current['reviewed_and_merged_tree'],'b054043db227ff00e7fe6d2be0db8e1ad6212b74')
            for field,value in [('repository_id',123),('revision','a'*40),('review_receipt_sha256','a'*64)]:
                write(dict(binding,**{field:value}),provenance)
                with self.subTest(field=field),self.assertRaises(ci.ContractError):ci.router_binding(root)
            for field,value in [('revision','short'),('merged_revision','b'*40),('reviewed_and_merged_tree',None),('review_receipt_sha256','b'*64)]:
                changed=copy.deepcopy(provenance);changed['incremental_sources'][0][field]=value;write(binding,changed)
                with self.subTest(field=field),self.assertRaises(ci.ContractError):ci.router_binding(root)
            changed=copy.deepcopy(provenance);changed['incremental_sources']=[];write(binding,changed)
            with self.assertRaises(ci.ContractError):ci.router_binding(root)
    def test_router_fetched_revision_tree_remote_and_cleanliness_before_execution(self):
        binding=ci.router_binding()
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw);(path/'.git').mkdir()
            valid=[binding['revision'],binding['reviewed_and_merged_tree'],'https://github.com/'+binding['repository'],b'']
            with patch.object(ci.subprocess,'check_output',side_effect=valid):ci.verify_router_checkout(binding,path)
            for index,value in [(0,'a'*40),(1,'b'*40),(2,'https://github.com/foreign/router'),(3,b' M tracked')]:
                output=list(valid);output[index]=value
                with self.subTest(index=index),patch.object(ci.subprocess,'check_output',side_effect=output),self.assertRaises(ci.ContractError):ci.verify_router_checkout(binding,path)
            # A failed source check cannot reach the command runner or router import path.
            with patch.object(ci,'verify_router_public_identity'),patch.dict(os.environ,AWA_CI_ROUTER_PATH=str(path)),patch.object(ci,'verify_router_checkout',side_effect=ci.ContractError('tree differs')),patch.object(ci,'bounded') as runner,self.assertRaises(ci.ContractError):
                ci.measured('router-seam',allow_cross_host=True)
            runner.assert_not_called()
    def test_router_public_identity_checks_actual_id_name_visibility_and_archive(self):
        binding={'repository':'KleinPerkins/intent-router','repository_id':123}
        valid={'id':123,'full_name':'KleinPerkins/intent-router','private':False,'archived':False}
        with patch.object(ci.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(valid).encode())):ci.verify_router_public_identity(binding)
        for mutation in [{'id':124},{'id':True},{'full_name':'KleinPerkins/other'},{'private':True},{'archived':True}]:
            with patch.object(ci.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(dict(valid,**mutation)).encode())),self.assertRaises(ci.ContractError):ci.verify_router_public_identity(binding)
    def test_metadata_read_token_is_scoped_to_exact_public_api_request(self):
        binding=ci.router_binding();valid={'id':binding['repository_id'],'full_name':binding['repository'],'private':False,'archived':False}
        with patch.dict(os.environ,CI_READ_TOKEN='metadata-only-fixture'),patch.object(ci.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(valid).encode())) as request:
            ci.verify_router_public_identity(binding)
        sent=request.call_args.args[0]
        self.assertEqual(sent.full_url,'https://api.github.com/repos/KleinPerkins/intent-router')
        self.assertEqual(sent.get_header('Authorization'),'Bearer metadata-only-fixture')
        with patch.dict(os.environ,CI_READ_TOKEN=''),patch.object(ci.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(valid).encode())) as request:
            ci.verify_router_public_identity(binding)
        self.assertIsNone(request.call_args.args[0].get_header('Authorization'))
class WorkflowTests(unittest.TestCase):
    def test_closed_required_native_and_disposable_lanes(self):
        workflow=json.loads((ROOT/'.github/workflows/ci.yml').read_bytes());jobs=workflow['jobs']
        self.assertEqual(set(jobs),set(ci.SHARDS)|{'ci-required'});self.assertEqual(jobs['ci-required']['needs'],list(ci.SHARDS));self.assertEqual(jobs['ci-required']['if'],'${{ always() }}')
        self.assertEqual(workflow['permissions'],{'contents':'read'});self.assertNotIn('pull_request_target',workflow['on'])
        for shard in ci.SHARDS:
            self.assertEqual(jobs[shard]['runs-on'],'macos-15' if ci.HOSTS[shard]=='Darwin' else 'ubuntu-24.04')
            self.assertIn('scripts/verify.py shard --shard '+shard,jobs[shard]['steps'][-1]['run'])
            for step in jobs[shard]['steps']:
                if 'uses' in step:self.assertRegex(step['uses'],r'@[0-9a-f]{40}$')
                if step.get('uses','').startswith('actions/checkout@'):self.assertIs(step['with']['persist-credentials'],False)
        seam=jobs['router-seam']['steps'];self.assertEqual(seam[2]['env'],{'CI_READ_TOKEN':'${{ github.token }}'});self.assertEqual(seam[-1]['env']['CI_READ_TOKEN'],'${{ github.token }}');self.assertTrue(all('CI_READ_TOKEN' not in step.get('env',{}) for step in seam if 'uses' in step));self.assertEqual(seam[2]['run'],'python3 -I -B scripts/verify.py router-binding');self.assertEqual(seam[3]['with']['ref'],'${{ steps.router.outputs.revision }}')
    def test_native_runtime_pin_preserves_sqlite_floor_and_other_lanes(self):
        workflow=json.loads((ROOT/'.github/workflows/ci.yml').read_bytes());c,_,_=ci.policy()
        self.assertEqual(c['runtime_requirements']['native_stock_sqlite_minimum'],'3.51.3')
        self.assertEqual(c['runtime_requirements']['native_python'],'3.15.2')
        for name in ci.SHARDS:
            setup=next(x for x in workflow['jobs'][name]['steps'] if x.get('uses','').startswith('actions/setup-python@'))
            self.assertEqual(setup['with']['python-version'],'3.15.2' if name=='source-native' else '3.14.6')
    def test_manual_receipt_mode_validates_required_pr_without_traceback(self):
        workflow=json.loads((ROOT/'.github/workflows/reviewer-app.yml').read_bytes())
        resolver=next(x for x in workflow['jobs']['admit']['steps'] if x.get('id')=='target')
        self.assertIn("inputs.mode == 'receipt'",resolver['if'])
        code='\n'.join(resolver['run'].splitlines()[1:-1])+'\n'
        with tempfile.TemporaryDirectory() as raw:
            event=Path(raw)/'event.json';output=Path(raw)/'output'
            env=dict(os.environ,GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_EVENT_PATH=str(event),GITHUB_OUTPUT=str(output))
            for value in ('','invalid',None,'-1','0','1000000000'):
                event.write_text(json.dumps({'inputs':{'mode':'receipt','pr':value}}))
                result=subprocess.run([sys.executable,'-I','-B','-'],input=code.encode(),env=env,capture_output=True)
                self.assertNotEqual(result.returncode,0);self.assertNotIn(b'Traceback',result.stderr);self.assertFalse(output.exists())
            event.write_text(json.dumps({'inputs':{'mode':'receipt','pr':'19'}}))
            result=subprocess.run([sys.executable,'-I','-B','-'],input=code.encode(),env=env,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(output.read_text(),'pr=19\n')
    def test_source_producers_are_bound_while_privileged_workflow_stays_flag_gated(self):
        registry=json.loads((ROOT/'.github/review-enrollments.json').read_bytes());self.assertIs(registry['enabled'],True);self.assertEqual({p['credential_store'] for p in registry['producers']},{'keyring','file'});self.assertEqual({p['origin_account'] for p in registry['producers']},{'origin-7612de79','origin-6a644d43'})
        for producer in registry['producers']:
            self.assertEqual(producer['capture_adapter_sha256'],ci.digest((ROOT/'scripts/local_review.py').read_bytes()))
            self.assertEqual(producer['creation_adapter_sha256'],ci.digest((ROOT/'scripts/create_review_pr.py').read_bytes()))
        workflow=json.loads((ROOT/'.github/workflows/reviewer-app.yml').read_bytes());self.assertTrue(workflow['jobs']['admit']['if'].startswith("vars.AWA_CI_ADAPTER_ENROLLED == 'true' && ("));self.assertIn('github.event.sender.id == 49759187',workflow['jobs']['admit']['if']);self.assertIn("github.ref == 'refs/heads/main'",workflow['jobs']['admit']['if']);self.assertIn("p['enabled'] is True",workflow['jobs']['admit']['steps'][1]['run'])
        for name,required in [('local_review.py',['repo','request','policy','enrollment','output']),('create_review_pr.py',['repo','request','policy','enrollment','review','title','body','output','journal'])]:
            args=[sys.executable,'-I','-B',str(ROOT/'scripts'/name)]
            for field in required:args+=['--'+field,str(ROOT) if field=='repo' else '/nonexistent/fixture']
            p=subprocess.run(args,capture_output=True);self.assertNotEqual(p.returncode,0);self.assertNotIn(b'Traceback',p.stderr)
if __name__=='__main__':unittest.main()
