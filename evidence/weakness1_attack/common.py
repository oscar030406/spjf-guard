"""Read-only development inputs and confined runtime setup."""
from pathlib import Path
import os
import sys
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
for key, value in {
    'PYTHONDONTWRITEBYTECODE': '1', 'NUMBA_NUM_THREADS': '4',
    'OMP_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '4', 'MKL_NUM_THREADS': '4',
    'NUMBA_CACHE_DIR': str(HERE / 'cache' / 'numba'),
    'MPLCONFIGDIR': str(HERE / 'cache' / 'matplotlib'),
    'TMP': str(HERE / 'cache' / 'tmp'), 'TEMP': str(HERE / 'cache' / 'tmp'),
}.items():
    os.environ[key] = value
(HERE / 'cache' / 'tmp').mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'src'))
if (HERE / 'pinned_src' / 'spjf_guard' / 'sim').is_dir():
    drift = json.loads((HERE / 'source_drift.json').read_text(encoding='utf-8'))
    for entry in drift['sources']:
        snapshot = HERE / entry['snapshot']
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == entry['baseline_sha256']
        if entry['path'].startswith(('src/spjf_guard/data/', 'src/spjf_guard/experiment/')):
            assert hashlib.sha256((ROOT / entry['path']).read_bytes()).hexdigest() == entry['baseline_sha256'], 'project data/experiment interface changed'
    sys.path.insert(0, str(HERE / 'pinned_src'))

import numpy as np
from spjf_guard.data import sealed
from spjf_guard.experiment.reproduce import load_overlay

TERMS = ('2020-ERE', '2020-2', '2021-1', '2021-2', '2022-1', '2022-2')


def development_input_path(rep=0):
    assert rep in range(5)
    original = ROOT / 'data' / 'derived' / 'overlay_traces' / f'primary_rep{rep}.npz'
    recovered = HERE / 'recovered_development_inputs.json'
    if recovered.exists():
        record = json.loads(recovered.read_text(encoding='utf-8'))
        if record.get('status') == 'PASS':
            row = record['inputs'][rep]
            assert row['rep'] == rep
            path = (HERE / row['recovered_path']).resolve()
            assert path.parent == (HERE / 'raw' / 'recovered_development').resolve()
            assert path.name == f'primary_rep{rep}.npz'
            return path
    return original


def development_overlay(rep=0):
    """Project guard before project loader, as in scripts/run_main.py.

    The only accepted filenames are the explicitly documented primary development
    overlays. The mixed event cache is never opened. The original cached expected
    cost predictor is retained, and is identified separately from a package refit.
    """
    assert rep in range(5)
    sealed.guard_semesters(TERMS, ROOT, unseal=False)
    path = development_input_path(rep)
    provenance = json.loads((HERE / 'development_inputs.json').read_text(encoding='utf-8'))
    assert provenance['terms'] == list(TERMS) and provenance['pool'] == 'primary'
    assert provenance['unseal'] is False
    expected = provenance['inputs'][rep]
    assert expected['rep'] == rep and Path(expected['path']).name == path.name
    assert path.stat().st_size == expected['bytes'], 'development input size changed'
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            digest.update(block)
    assert digest.hexdigest() == expected['sha256'], 'development input hash changed; refusing to parse'
    trace, _, labels = load_overlay(path, level=0, limit_s=60.)
    with np.load(path) as z:
        labels['week'] = z['wk'].astype(np.int64)
        labels['n_weeks'] = int(len(z['weeks']))
        labels['week_axis'] = [int(value) for value in z['weeks']]
        labels['busy_hour_work_s'] = float(z['W'])
        labels['copies'] = int(z['copies'])
    return trace, labels


def save_json(name, obj):
    import json
    (HERE / name).write_text(json.dumps(obj, indent=2, allow_nan=False), encoding='utf-8')


def timing(start_wall, start_cpu):
    import time
    return {'wall_s': time.perf_counter() - start_wall, 'cpu_s': time.process_time() - start_cpu}
