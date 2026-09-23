"""Recover the recorded code version without changing concurrent repository work."""
import sys
sys.dont_write_bytecode=True
from common import HERE, ROOT
import ast
import hashlib
import json
import subprocess
import time
from datetime import datetime,timezone

CHANGED_ALLOWED={'src/spjf_guard/sim/runner.py','src/spjf_guard/sim/policy.py','configs/main.yaml'}
PIN=HERE/'pinned_src'/'spjf_guard'
SIM_FILES=('__init__.py','runner.py','policy.py','kernel.py','bounds.py','reference.py','tightness.py')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git_bytes(path):
    return subprocess.run(['git','--no-optional-locks','show','HEAD:'+path],cwd=ROOT,
                          check=True,capture_output=True).stdout


def recover(path,expected):
    raw=git_bytes(path)
    variants=(raw,raw.replace(b'\r\n',b'\n'),raw.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
    for candidate in variants:
        if sha(candidate)==expected:
            return candidate
    raise RuntimeError('Git content cannot reproduce the recorded version of '+path)


class RemoveAgeExtension(ast.NodeTransformer):
    def visit_AnnAssign(self,node):
        if isinstance(node.target,ast.Name) and node.target.id=='age_credit_per_s':
            return None
        return self.generic_visit(node)
    def visit_If(self,node):
        if any(isinstance(n,ast.Attribute) and n.attr=='age_credit_per_s' for n in ast.walk(node.test)):
            return None
        return self.generic_visit(node)
    def visit_FunctionDef(self,node):
        if node.name=='aging':
            return None
        return self.generic_visit(node)


def main():
    wall,cpu=time.perf_counter(),time.process_time()
    baseline=json.loads((HERE/'source_baseline.json').read_text(encoding='utf-8-sig'))
    recovered={}
    rows=[]
    for entry in baseline['sources']:
        path=entry['path']
        current=(ROOT/path).read_bytes()
        same=sha(current)==entry['sha256']
        assert same or path in CHANGED_ALLOWED,path
        original=current if same else recover(path,entry['sha256'])
        recovered[path]=original
        row={'path':path,'baseline_sha256':entry['sha256'],'current_sha256':sha(current),
             'current_matches_baseline':same,'last_write_unix':(ROOT/path).stat().st_mtime}
        if not same and path.endswith('.py'):
            old_tree=ast.parse(original.decode('utf-8'))
            new_tree=RemoveAgeExtension().visit(ast.parse(current.decode('utf-8')))
            assert ast.dump(old_tree,include_attributes=False)==ast.dump(new_tree,include_attributes=False),path
            row['AST_identical_after_removing_age_extension']=True
        rows.append(row)
    from spjf_guard.sim.policy import fcfs,sjf,spjf,guard
    checked=[fcfs(),sjf(),spjf('tweedie')]+[
        guard(g,k,60,b*k,e,'tweedie',gam_s=q*k)
        for k in range(1,77) for g,b,e,q in [(300,15,.5,0),(600,30,.75,0),(1200,0,0,4)]]
    assert all(getattr(p,'age_credit_per_s',0)==0 for p in checked)
    (PIN/'sim').mkdir(parents=True,exist_ok=True)
    (PIN/'__init__.py').write_text(
        '"""Pinned scheduling modules with read-only fallback to project data loaders."""\n'
        'from pathlib import Path\n'
        '__path__.append(str(Path(__file__).resolve().parents[4] / "src" / "spjf_guard"))\n'
        '__version__ = "0.1.0"\n',encoding='utf-8')
    for name in SIM_FILES:
        path='src/spjf_guard/sim/'+name
        raw=recovered.get(path)
        if raw is None:
            raw=git_bytes(path)
        (PIN/'sim'/name).write_bytes(raw)
    snapshots=[]
    for row in rows:
        path=row['path']
        if path.startswith('src/spjf_guard/sim/'):
            snapshot=PIN/'sim'/Path(path).name
        else:
            snapshot=HERE/'source_snapshot'/path
            snapshot.parent.mkdir(parents=True,exist_ok=True)
            snapshot.write_bytes(recovered[path])
        assert sha(snapshot.read_bytes())==row['baseline_sha256']
        row['snapshot']=str(snapshot.relative_to(HERE)).replace('\\','/')
        snapshots.append(row)
    report={'status':'PASS','recorded_utc':datetime.now(timezone.utc).isoformat(),
            'sources':snapshots,'zero_age_credit_policies_checked':len(checked),
            'interpretation':'Concurrent changes add an optional age-credit ranking. All frozen study policies have zero credit. Capacity workers imported before this edit; subsequent study replays use the hash-matched baseline simulation snapshot. Current repository files are untouched.',
            'config_scope':'The experiment uses its frozen parameter literals and cached tweedie arrays, not the newly changed headline predictor configuration.',
            'timing':{'wall_s':time.perf_counter()-wall,'cpu_s':time.process_time()-cpu}}
    text=json.dumps(report,indent=2)+'\n'
    (HERE/'source_drift.json').write_text(text,encoding='utf-8')
    (HERE/'out_audit_source_drift.txt').write_text(text,encoding='utf-8')
    print(text)


if __name__=='__main__':
    from pathlib import Path
    main()
