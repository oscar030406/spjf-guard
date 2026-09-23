"""Inspect the actual cross-process timestamp clock implementation before acceptance."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import json
import time
import platform

HERE = Path(__file__).resolve().parent
wall, cpu = time.perf_counter(), time.process_time()
report = {'python': platform.python_version(), 'clocks': {}}
for name in ('monotonic', 'perf_counter', 'process_time'):
    info = time.get_clock_info(name)
    clock = getattr(time, name + '_ns')
    values = [clock() for _ in range(10000)]
    increments = [b-a for a,b in zip(values, values[1:]) if b>a]
    report['clocks'][name] = {
        'implementation': info.implementation, 'resolution_s': info.resolution,
        'monotonic': info.monotonic, 'adjustable': info.adjustable,
        'different_samples': len(set(values)),
        'minimum_observed_positive_increment_ns': min(increments) if increments else None,
    }
report['execution'] = {'wall_s': time.perf_counter()-wall, 'cpu_s': time.process_time()-cpu}
text = json.dumps(report, indent=2) + '\n'
(HERE / 'clock_resolution.json').write_text(text, encoding='utf-8')
(HERE / 'out_clock_resolution.txt').write_text(text, encoding='utf-8')
print(text)
