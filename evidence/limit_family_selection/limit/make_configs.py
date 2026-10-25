"""Copy configs/main.yaml byte for byte, changing only the value of clock.limit_s.

    python evidence/limit_family_selection/limit/make_configs.py
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[2] / "configs" / "main.yaml"
OLD = b"  limit_s: 60.0 "

text = SOURCE.read_bytes()
assert text.count(OLD) == 1
for limit in (45, 60, 90, 120):
    (HERE / f"main_L{limit}.yaml").write_bytes(text.replace(OLD, f"  limit_s: {limit}.0 ".encode()))
