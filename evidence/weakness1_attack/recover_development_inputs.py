"""Recover original development overlays from a documented additive cache rebuild."""
import sys
sys.dont_write_bytecode=True
from common import HERE,ROOT,TERMS
from spjf_guard.data import sealed
from spjf_guard.experiment.reproduce import load_overlay
import hashlib
import json
import time
import zipfile
import copy
from pathlib import Path

ADDED_MEMBERS={'copy_entry.npy','copy_round.npy','tweedie_conservative.npy',
               'log_conservative.npy','tweedie_static.npy','log_static.npy'}
DEST=HERE/'raw'/'recovered_development'


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def main():
    wall,cpu=time.perf_counter(),time.process_time()
    allowed=json.loads((HERE/'development_inputs.json').read_text(encoding='utf-8'))
    assert allowed['unseal'] is False and allowed['pool']=='primary' and allowed['terms']==list(TERMS)
    DEST.mkdir(parents=True,exist_ok=True)
    results=[]
    for original in allowed['inputs']:
        target=DEST/f"primary_rep{original['rep']}.npz"
        if target.exists() and digest(target)==original['sha256']:
            results.append({**original,'recovered_path':str(target.relative_to(HERE)).replace('\\','/'),'status':'reused_exact_hash'})
            continue
        sealed.guard_semesters(TERMS,ROOT,unseal=False)
        source=ROOT/original['path']
        # The guarded project path admits only this explicitly documented development pool.
        tr,_,labels=load_overlay(source,level=0,limit_s=60.)
        assert len(tr)==17_634_760 and int(labels['in_window'].sum())==4_219_556
        assert int(tr.service_us.max())<=60_000_000 and int(tr.service_us.min())>0
        del tr,labels
        source_hash=digest(source)
        tmp=target.with_suffix('.candidate.npz')
        with zipfile.ZipFile(source,'r') as zin,zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as zout:
            names=set(zin.namelist())
            assert ADDED_MEMBERS.issubset(names),(source,names)
            for member in zin.infolist():
                if member.filename in ADDED_MEMBERS:
                    continue
                preserved=copy.copy(member)
                with zin.open(member,'r') as fin,zout.open(preserved,'w',force_zip64=True) as fout:
                    for block in iter(lambda:fin.read(1024*1024),b''):
                        fout.write(block)
        recovered_hash=digest(tmp)
        row={**original,'source_rebuild_sha256':source_hash,
             'source_rebuild_bytes':source.stat().st_size,
             'recovered_path':str(target.relative_to(HERE)).replace('\\','/'),
             'candidate_sha256':recovered_hash,'candidate_bytes':tmp.stat().st_size,
             'removed_members':sorted(ADDED_MEMBERS),
             'source':'documented local development cache rebuild; no network retrieval',
             'status':'exact_original_hash' if recovered_hash==original['sha256'] else 'hash_mismatch'}
        results.append(row)
        (HERE/'recovered_development_inputs.json').write_text(json.dumps({'inputs':results},indent=2),encoding='utf-8')
        print(json.dumps(row),flush=True)
        if recovered_hash!=original['sha256']:
            raise RuntimeError('original input not recovered byte-for-byte; candidate preserved and not accepted')
        tmp.replace(target)
    result={'status':'PASS','inputs':results,'timing':{'wall_s':time.perf_counter()-wall,'cpu_s':time.process_time()-cpu}}
    text=json.dumps(result,indent=2)+'\n'
    (HERE/'recovered_development_inputs.json').write_text(text,encoding='utf-8')
    print(text)


if __name__=='__main__':
    main()
