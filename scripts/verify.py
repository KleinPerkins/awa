#!/usr/bin/env python3
"""AWA source CI adapter. Preserves the owner runner; no host/runtime activation.
Identity, bounded process cleanup and fail-closed aggregate adapted from qualified
KleinPerkins/dev d57009cb; receipts are operational measurements, not attestations.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, platform, re, selectors, shutil, signal, sqlite3, stat, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SHARDS=('source-portable','source-native','install-fixture','dashboard','router-seam','review-admission')
NAMES=('KleinPerkins/awa',)
IDENTITY_KEYS=('repository','repository_id','event','revision','workflow_sha','run_id','run_attempt','ref','head_sha','base_sha','workflow_ref','workflow')
MAX_OUTPUT=8*1024*1024
COMMANDS={
 'source-portable':['make','verify'], 'source-native':['make','verify'],
 'install-fixture':['make','verify-install'],
 'dashboard':['python3','-B','dashboard/test_render.py'],
 'router-seam':['python3', '-B', '-m', 'unittest', '-v', 'engine.tests.test_consumer_seam', 'engine.tests.test_consumer_golden.TestGoldenAgainstRealRouter', 'engine.tests.test_consumer_loop.TestOperatorLoop.test_real_router_benign_status_reads', 'engine.tests.test_consumer_loop.TestOperatorLoop.test_real_router_destructive_utterance_confirms', 'engine.tests.test_consumer_trial_runner.TestRouterLifecycleSeam'],
 'review-admission':['python3','-B','-m','unittest','discover','-v','-s','tests','-p','test_*.py']}
HOSTS={'source-portable':'Linux','source-native':'Darwin','install-fixture':'Darwin','dashboard':'Linux','router-seam':'Linux','review-admission':'Linux'}
class ContractError(ValueError): pass

def require(ok, reason):
    if not ok: raise ContractError(reason)

def digest(data): return hashlib.sha256(data).hexdigest()

def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':')).encode()

def closed(value, fields):
    require(isinstance(value,dict) and set(value)==set(fields.split()),'closed schema fields differ')

def parse(raw):
    def unique(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,'duplicate JSON key');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=unique)

def identity(environment):
    names=('GITHUB_REPOSITORY','GITHUB_REPOSITORY_ID','GITHUB_EVENT_NAME','GITHUB_SHA','GITHUB_WORKFLOW_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_REF','CI_HEAD_SHA','CI_BASE_SHA','GITHUB_WORKFLOW_REF','GITHUB_WORKFLOW')
    v={k:environment.get(n,'') for k,n in zip(IDENTITY_KEYS,names)}
    require(v['repository'] in NAMES and v['repository_id']=='1289571438','wrong repository phase/ID')
    require(v['event'] in ('push','pull_request','workflow_dispatch'),'unsupported CI event')
    for k in ('revision','workflow_sha'):require(re.fullmatch('[0-9a-f]{40}',v[k]),'invalid '+k)
    for k in ('run_id','run_attempt'):require(re.fullmatch('[1-9][0-9]*',v[k]),'invalid '+k)
    if v['event']=='pull_request':
        require(re.fullmatch(r'refs/pull/[1-9][0-9]*/merge',v['ref']),'expected merge ref')
        for k in ('head_sha','base_sha'):require(re.fullmatch('[0-9a-f]{40}',v[k]),'invalid '+k)
    else:require(v['ref']=='refs/heads/main' and v['head_sha']==v['base_sha']=='','invalid main source tuple')
    require(v['workflow']=='CI' and v['workflow_sha']==v['revision'],'wrong tested workflow')
    require(v['workflow_ref']==v['repository']+'/.github/workflows/ci.yml@'+v['ref'],'workflow phase/path/ref mismatch')
    return v

def check_checkout(expected):
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==expected['revision'],'checkout differs')
    if expected['event']=='pull_request':
        require(subprocess.check_output(['git','show','-s','--format=%P','HEAD'],cwd=ROOT,text=True).split()==[expected['base_sha'],expected['head_sha']],'merge parent ordering differs')

def bounded(argv,timeout,cwd=ROOT,overrides=None):
    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    for k in list(env):
        # Shell startup files/functions can silently displace fixture PATH stubs.
        if k.startswith(('GIT_', 'BASH_FUNC_', 'AWA_')) or k in ('BASH_ENV', 'ENV','PYTHONPATH','PYTHONHOME',
                'GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'):
            env.pop(k)
    env.update(overrides or {})
    p=subprocess.Popen(argv,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    out=bytearray();selector=selectors.DefaultSelector();selector.register(p.stdout,selectors.EVENT_READ);deadline=time.monotonic()+timeout
    try:
        while selector.get_map():
            require(time.monotonic()<deadline,'command timeout')
            for key,_ in selector.select(min(.25,max(0,deadline-time.monotonic()))):
                data=os.read(key.fileobj.fileno(),65536)
                if not data:selector.unregister(key.fileobj);continue
                out.extend(data);require(len(out)<=MAX_OUTPUT,'command output exceeded bound')
        p.wait(timeout=max(.1,deadline-time.monotonic()))
        require(p.returncode==0,'command failed: '+str(argv)+'\n'+out.decode(errors='replace'))
        return bytes(out)
    finally:
        try:os.killpg(p.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:p.wait(timeout=2)
        except subprocess.TimeoutExpired:pass
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        p.wait();selector.close();p.stdout.close()

def validate_aggregate(needs,expected):
    c,m,hash_=policy()
    require(isinstance(needs,dict) and set(needs)==set(SHARDS),'missing or extra shard')
    for shard in SHARDS:
        row=needs[shard];closed(row,'result outputs');require(row['result']=='success','shard failed/skipped/cancelled')
        closed(row['outputs'],'receipt');receipt=parse(row['outputs']['receipt']);closed(receipt,'schema shard identity result measurement')
        require(receipt['schema']=='awa-ci-shard/v1' and receipt['shard']==shard and receipt['identity']==expected and receipt['result']=='success','stale shard receipt')
        validate_measurement(receipt['measurement'],shard,c,m,hash_)
    return hash_

def policy(root=ROOT):
    raw=(root/'.github/ci-contract.json').read_bytes();c=parse(raw)
    mraw=(root/'.github/test-shards.json').read_bytes();m=parse(mraw)
    require(c['schema']=='awa-ci-contract/v1' and c['repository_id']==1289571438 and c['repository_names']==list(NAMES),'CI repository identity')
    require(c['shards']==list(SHARDS) and c['commands']==COMMANDS and c['hosts']==HOSTS,'missing/reassigned source gate')
    require(m=={'schema':'awa-test-sharding/v1','state':'prepared-router-source-required','aggregate':'ci-required','shards':list(SHARDS)},'shard topology differs')
    for name,sha in c['preserved_source_sha256'].items():
        require(digest((root/name).read_bytes())==sha,'owner source changed: '+name)
    require(c['engine_modules']==sorted(str(p.relative_to(root)) for p in (root/'engine/tests').glob('test_*.py')),'engine module inventory changed')
    require(c['adapter_tests']==sorted(str(p.relative_to(root)) for p in (root/'tests').glob('test_*.py')),'adapter test inventory changed')
    allowed=c.get('native_allowed_skip_ids')
    require(isinstance(allowed,list) and allowed==sorted(set(allowed)) and len(allowed)==15
            and all(isinstance(case,str) and re.fullmatch(r'engine\.tests\.test_consumer_[A-Za-z0-9_.]+',case) for case in allowed),'invalid native skip-ID policy')
    return c,m,digest(raw+b'\0'+mraw)

def router_binding(root=ROOT):
    binding=parse((root/'.github/router-ci-source.json').read_bytes())
    closed(binding,'schema enabled repository repository_id revision review_receipt_sha256 public_source reason')
    require(binding['schema']=='awa-router-ci-source/v1' and binding['repository']=='KleinPerkins/intent-router','router source owner changed')
    require(binding['enabled'] is True and binding['public_source'] is True,'required seam prerequisite unavailable: exact reviewed accessible router source is not enrolled')
    require(type(binding['repository_id']) is int and binding['repository_id']==1294651532,'router immutable source identity differs')
    for key,n in [('revision',40),('review_receipt_sha256',64)]:
        require(isinstance(binding[key],str) and re.fullmatch('[0-9a-f]{'+str(n)+'}',binding[key]),'reviewed exact router binding required')
    provenance=parse((root/'.github/ci-adapter-provenance.json').read_bytes())
    require(isinstance(provenance,dict) and provenance.get('schema')=='awa-ci-adapter-provenance/v1','invalid adapter provenance')
    sources=provenance.get('incremental_sources')
    require(isinstance(sources,list) and all(isinstance(s,dict) for s in sources),'invalid source provenance')
    matches=[s for s in sources if s.get('repository')==binding['repository']]
    require(len(matches)==1,'router source provenance missing or duplicated')
    source=matches[0]
    for key,n in [('revision',40),('merged_revision',40),('reviewed_and_merged_tree',40),('review_receipt_sha256',64)]:
        require(isinstance(source.get(key),str) and re.fullmatch('[0-9a-f]{'+str(n)+'}',source[key]),'reviewed router provenance malformed')
    require(binding['revision']==source['merged_revision'] and binding['review_receipt_sha256']==source['review_receipt_sha256'],'router binding differs from reviewed provenance')
    # Receipt digest remains an audit commitment; no receipt bytes are loaded here.
    # The reviewed source policy, not a second hardcoded revision, is the trust root.
    return dict(binding,reviewed_head=source['revision'],reviewed_and_merged_tree=source['reviewed_and_merged_tree'])

def verify_router_checkout(binding,path):
    require((path/'.git').exists(),'exact router checkout required')
    require(subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()==binding['revision'],'router checkout revision differs')
    require(subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD^{tree}'],text=True).strip()==binding['reviewed_and_merged_tree'],'router checkout tree differs from reviewed tree')
    remote=subprocess.check_output(['git','-C',str(path),'remote','get-url','origin'],text=True).strip()
    require(remote in ['https://github.com/'+binding['repository'], 'https://github.com/'+binding['repository']+'.git','git@github.com:'+binding['repository']+'.git'],'router remote identity differs')
    require(not subprocess.check_output(['git','-C',str(path),'status','--porcelain']),'dirty router checkout')

def verify_router_public_identity(binding):
    request=urllib.request.Request('https://api.github.com/repos/'+binding['repository'],headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    with urllib.request.urlopen(request,timeout=20) as response:
        raw=response.read(65537)
    require(len(raw)<=65536,'router source metadata exceeds bound')
    observed=parse(raw)
    require(type(observed.get('id')) is int and observed['id']==binding['repository_id'] and observed.get('full_name')==binding['repository'] and observed.get('private') is False and observed.get('archived') is False,'router source identity/accessibility differs')

def validate_native_skips(skips,contract):
    # The off-switch corpus deliberately excludes router code; its fifteen exact
    # cases run without skips in router-seam. No reason text can waive a native test.
    allowed=set(contract['native_allowed_skip_ids'])
    require(all(item['case'] in allowed for item in skips),'required native case skipped')

def private_fixture_base():
    # Darwin secure-walk fixtures reject /tmp; dashboard fixtures reject /Users.
    # Resolve the operating system's private user temp, never change product assertions.
    if platform.system()=='Darwin':
        raw=subprocess.check_output(['/usr/bin/getconf','DARWIN_USER_TEMP_DIR'],text=True,timeout=5).strip()
        require(raw and Path(raw).is_absolute() and '/Users/' not in raw,'Darwin private OS temp required')
        base=Path(raw).resolve()
    else:base=ROOT.parent.resolve()
    for parent in (base,*base.parents):
        info=parent.stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0,os.getuid()) and not info.st_mode & 0o022,'fixture ancestor is untrusted or group/other writable')
    return base

def measured(shard,allow_cross_host=False):
    c,m,contract=policy()
    require(allow_cross_host or platform.system()==HOSTS[shard],'required host differs: '+HOSTS[shard])
    if shard=='source-native':
        require(sqlite3.sqlite_version_info >= (3,51,3), 'native registration coverage requires stock SQLite >=3.51.3')
        require(shutil.which('chflags') is not None, 'native immutable-file coverage requires chflags')
    with tempfile.TemporaryDirectory(prefix='awa-ci-private-',dir=private_fixture_base()) as temporary:
        private=Path(temporary);home=private/'home';home.mkdir(mode=0o700);scratch=private/'tmp';scratch.mkdir(mode=0o700)
        receipt=private/'engine-receipt.json'
        env={'HOME':str(home),'TMPDIR':str(scratch),'XDG_DATA_HOME':str(home/'data'),'XDG_CONFIG_HOME':str(home/'config'),'XDG_STATE_HOME':str(home/'state'),'XDG_CACHE_HOME':str(home/'cache')}
        if shard.startswith('source-'):
            require(importlib.util.find_spec('intent_router') is None,'off-switch source lane requires router absent')
            env['AWA_PERFORMANCE_RECEIPT']=str(receipt)
        if shard=='router-seam':
            binding=router_binding();verify_router_public_identity(binding);path=Path(os.environ.get('AWA_CI_ROUTER_PATH','')).resolve()
            verify_router_checkout(binding,path)
            env.update(PYTHONPATH=str(ROOT)+os.pathsep+str(path),AWA_SEAM_REQUIRE_ROUTER='1',AWA_TRIAL_REQUIRE_ROUTER_LIFECYCLE='1',AWA_TRIAL_ROUTER_SOURCE=str(path))
        output=bounded(COMMANDS[shard],3600,overrides=env);print(output.decode(errors='replace'))
        skips=[];count=None;case_digest=None
        if shard.startswith('source-'):
            sys.path.insert(0,str(ROOT))
            from engine.tests.verification_contract import validate_receipt
            owner=parse(receipt.read_bytes());validate_receipt(owner)
            require(owner['run']['outcome']=='passed' and owner['context']['selectors']==[] and owner['test_count']>0,'full source corpus receipt required')
            count=owner['test_count'];case_digest=owner['inventory_sha256']
            skips=[{'case':record['test_id'],'reason':record['skip_reason']} for record in owner['records'] if record['outcome']=='skipped']
            require(len(skips)<count,'all source cases skipped')
            if shard=='source-native':
                validate_native_skips(skips,c)
        else:
            counts=re.findall(rb'Ran ([0-9]+) tests? in ',output)
            require(counts,'test runner did not report executed cases')
            count=sum(map(int,counts));require(count>0,'zero test cases')
            # These dedicated lanes require every selected test to run.
            require(not re.search(rb'(?:skipped=|\.\.\. skipped )',output),'dedicated source lane skipped cases')
            ids=re.findall(rb'^START (\S+)\s*$',output,re.MULTILINE)
            if not ids:
                ids=[name+b' ('+scope+b')' for name,scope in re.findall(rb'^(\S+) \(([^\n]+)\)(?: \.\.\.|$)',output,re.MULTILINE)]
            require(len(ids)==count and len(set(ids))==count,'case identity evidence incomplete')
            case_digest=digest(canonical(sorted(case.decode() for case in ids)))
        return {'commands':[COMMANDS[shard]],'case_count':count,'case_ids_sha256':case_digest,'skips':skips,'logs_sha256':digest(output),'contract_sha256':contract,'host':platform.system(),'architecture':platform.machine()}

def validate_measurement(value,shard,c,m,hash_):
    closed(value,'commands case_count case_ids_sha256 skips logs_sha256 contract_sha256 host architecture')
    require(value['commands']==[COMMANDS[shard]] and value['contract_sha256']==hash_,'stale/missing gate evidence')
    require(value['host']==HOSTS[shard] and isinstance(value['architecture'],str) and value['architecture'],'required host coverage absent')
    require(type(value['case_count']) is int and value['case_count']>0,'zero cases')
    for key in ('case_ids_sha256','logs_sha256'):require(isinstance(value[key],str) and re.fullmatch('[0-9a-f]{64}',value[key]),'measurement digest missing')
    require(isinstance(value['skips'],list) and len(value['skips'])<value['case_count'],'all cases skipped')
    if not shard.startswith('source-'):require(not value['skips'],'required dedicated lane skipped')
    for skip in value['skips']:
        closed(skip,'case reason');require(all(isinstance(x,str) and x for x in skip.values()),'skip ledger incomplete')
        if shard=='source-native':validate_native_skips([skip],c)

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('local','shard','aggregate','router-binding'));p.add_argument('--shard',choices=SHARDS);p.add_argument('--allow-cross-host',action='store_true');a=p.parse_args()
    if a.mode=='router-binding':
        require(a.shard is None and not a.allow_cross_host,'unexpected option');binding=router_binding();verify_router_public_identity(binding)
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:
            f.write('repository='+binding['repository']+'\nrevision='+binding['revision']+'\n')
        return
    require(a.mode=='local' or not a.allow_cross_host,'cross-host evidence is local/non-authoritative only')
    if a.mode=='local':
        require(a.shard is not None,'choose an explicit local lane')
        print(json.dumps({'shard':a.shard,'measurement':measured(a.shard,a.allow_cross_host),'host_qualified':platform.system()==HOSTS[a.shard]},sort_keys=True));return
    expected=identity(dict(os.environ));check_checkout(expected)
    if a.mode=='shard':
        require(a.shard is not None,'shard required');result=measured(a.shard)
        receipt={'schema':'awa-ci-shard/v1','shard':a.shard,'identity':expected,'result':'success','measurement':result}
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('receipt='+canonical(receipt).decode()+'\n')
    else:
        require(a.shard is None,'aggregate cannot select shard');contract=validate_aggregate(parse(os.environ.get('CI_NEEDS','null')),expected)
        print('AWA_CI_AGGREGATE_V1 '+canonical({'schema':'awa-ci-aggregate/v1','identity':expected,'result':'success','contract_sha256':contract}).decode())
if __name__=='__main__':
    try:main()
    except (ContractError,ValueError,OSError,subprocess.SubprocessError,KeyError,TypeError) as e:
        print('AWA CI refused: '+str(e),file=sys.stderr);sys.exit(1)
