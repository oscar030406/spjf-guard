"""Check the inherited outage clock and raw input integrity."""
import sys
sys.dont_write_bytecode = True
from common import *

log, finish = log_start('diagnose')
d = pd.read_csv(RAW, sep=r'\s+', comment=';', header=None, names=COLS)
meta = json.loads((HERE/'download.json').read_text(encoding='utf-8-sig'))
assert hashlib.sha256(RAW.read_bytes()).hexdigest() == meta['sha256']
assert RAW.stat().st_size == meta['bytes']
log('DOWNLOAD VERIFIED', meta)
long = d[(d.queue==1)&(d.run>0)&(d.wait>DAY)]
log('LONG TEST WAITS BY RAW SWF DAY', long.groupby(long.submit//DAY).size().to_dict())
log('LONG TEST WAITS BY SHIFTED DAY', long.groupby((long.submit-d.submit.min())//DAY).size().to_dict())
for clock in ['raw','shifted']:
    a=d.submit-(0 if clock=='raw' else d.submit.min())
    kept=d[(d.run>0)&~((a>=138*DAY)&(a<153*DAY))]
    log(clock, 'retained',len(kept),'test wait',stats(kept[kept.queue==1].wait))
log('PARTITION SPANS', d.groupby('part').submit.agg(['min','max']).to_dict())
finish()
