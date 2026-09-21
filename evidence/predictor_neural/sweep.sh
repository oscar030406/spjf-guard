set -e
PY="D:/environment/tools/ml-env/python.exe"
R="env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME $PY train_neural.py --seed 3 --epochs 30 --tag _sweep"
for lr in 1e-3 3e-4; do
  for wd in 0 1e-4 1e-3; do
    $R --model N0 --lr $lr --wd $wd  > /dev/null 2>&1
    for agg in mean sum; do
      $R --model G1 --lr $lr --wd $wd --agg $agg > /dev/null 2>&1
    done
  done
done
