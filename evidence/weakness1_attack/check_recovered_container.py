"""Test whether NPZ serialization alone explains the rejected recovery candidate."""
import sys
sys.dont_write_bytecode=True
from common import HERE,ROOT,TERMS
from spjf_guard.data import sealed
import numpy as np
import hashlib,json,time

REP=0


def main():
    wall,cpu=time.perf_counter(),time.process_time()
    sealed.guard_semesters(TERMS,ROOT,unseal=False)
    source=HERE/'raw/recovered_development'/f'primary_rep{REP}.candidate.npz'
    target=source.with_name(f'primary_rep{REP}.numpy_serialization.npz')
    with np.load(source,allow_pickle=False) as z:
        arrays={name:z[name] for name in z.files}
    np.savez(target,**arrays)
    digest=hashlib.sha256()
    with target.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            digest.update(block)
    expected=json.loads((HERE/'development_inputs.json').read_text(encoding='utf-8'))['inputs'][REP]['sha256']
    result={'rep':REP,'candidate_sha256':digest.hexdigest(),'expected_sha256':expected,
            'matches':digest.hexdigest()==expected,'array_keys':list(arrays),
            'timing':{'wall_s':time.perf_counter()-wall,'cpu_s':time.process_time()-cpu}}
    text=json.dumps(result,indent=2)+'\n'
    (HERE/'container_serialization_check.json').write_text(text,encoding='utf-8')
    (HERE/'out_check_recovered_container.txt').write_text(text,encoding='utf-8')
    print(text)


if __name__=='__main__':
    main()
