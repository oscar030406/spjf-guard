# data

This package contains no raw data. The manuscript's Data Availability Statement says we
redistribute none of the source datasets, so each one has to be downloaded from its
publisher and saved at the path given below. The code reads these paths as written
(the `data` section of `configs/main.yaml`, relative to the package root).

## Datasets

| Dataset | Used for | Where to get it | Save as | Terms |
|---|---|---|---|---|
| CodeBench v1.81, Universidade Federal do Amazonas: 18 semesters, 2016-1 to 2024-1 | the main experiment (Sections 4, 7, 8) | <https://codebench.icomp.ufam.edu.br/dataset/> | `data/codebench/archives/cb_dataset_<semester>_v1.81.tar.gz`, one archive per semester | no licence stated on the page; cite the dataset; do not redistribute |
| ACcoding v1.0.0 (Chen et al., *Scientific Data* 2024, doi:10.1038/s41597-024-03392-z) | second grading log (Sections 4.3, 7, 8.6) | <https://zenodo.org/record/6522395>, doi:10.5281/zenodo.6522395 | `data/accoding/ACcoding-Dataset-v1.0.0.zip`; unzip it, unzip the `ACcoding.zip` inside, put the six `*.sql` files in `data/accoding/raw/`, then run `python evidence/accoding/parse_sql.py`, which writes `data/accoding/parquet/` | the data descriptor states CC BY 4.0; the Zenodo record lists "other (open)" |
| OULAD (Kuzilek et al., *Scientific Data* 2017, doi:10.1038/sdata.2017.171) | Table 4 and Section 7.2 only | <https://analyse.kmi.open.ac.uk/open_dataset> | the seven csv files directly under `data/` | CC BY 4.0 |
| Azure Functions Invocation Trace 2021 | serverless rows of Tables 4, 9, S1 and S3 | <https://github.com/Azure/AzurePublicDataset/blob/master/AzureFunctionsInvocationTrace2021.md>; cite Zhang et al., SOSP 2021, doi:10.1145/3477132.3483580 | `data/azure_functions_2021/AzureFunctionsInvocationTraceForTwoWeeksJan2021.rar`, extracted in place to `AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt` | CC BY 4.0 |
| Intel Netbatch 2012, pool D (Parallel Workloads Archive) | compute-farm rows of Tables 4, 9, S1 and S3 | <https://www.cs.huji.ac.il/labs/parallel/workload/l_intel_netbatch/>; cite Shai, Shmueli and Feitelson, JSSPP 2013, doi:10.1007/978-3-662-43779-7_7 | `data/intel_netbatch_2012/Intel-NetbatchD-2012-1.swf.gz` | free for research; acknowledge Ohad Shai, Edi Shmueli and Nir Antebi (Intel); do not redistribute |
| LPC-EGEE 2004 (Parallel Workloads Archive) | Supplementary Sections S6.4, S6.6, S6.7 | <https://www.cs.huji.ac.il/labs/parallel/workload/l_lpc/> | `evidence/lpc_egee/raw/LPC-EGEE-2004-1.2-cln.swf.gz` | free for research; acknowledge Emmanuel Medernach (data provider) and the Parallel Workloads Archive |
| Mozilla Firefox CI, two hardware worker pools | the recorded-wait check of Sections 7.2 and 8.6, Supplementary S2.2–S2.3 | collected from the public, unauthenticated Taskcluster and Treeherder APIs by `evidence/firefox_ci/run_collect.sh` | `data/mozilla_firefox_ci/` (written by that script) | no licence statement; attributed to Mozilla; not redistributed |

The sealed CodeBench semesters 2023-1, 2023-2 and 2024-1 are read only by the frozen
procedure in `docs/sealed_run_procedure.md`; without the `--unseal` flag and the
protocol lock, the code refuses to open them.

## Checksums of the files we used

SHA-256, computed on 2026-09-29 from the files the reported runs read. The three sealed
archives match the hashes recorded in `protocol_lock.json` at the freeze. The Firefox CI
slice has no checksum: the API expires old pages, so a new download is not byte-identical.

```text
777d5d30343575ef007ec92afab4e177969652ba0d730c96aeaa1b8a514d5d13  data/codebench/archives/cb_dataset_2016_1_v1.81.tar.gz
a7792403accd6aadbe47b04f48858a2da42574b98a78a3c245b7eaec4a92075f  data/codebench/archives/cb_dataset_2016_2_v1.81.tar.gz
cf8a9233b6464f688c9781b95930d7df4d19f47327dab1aedba6ba55d4337d63  data/codebench/archives/cb_dataset_2017_1_v1.81.tar.gz
545eef0e7b04820d127bdac3b5edfd9fda16cbb4617db6f07c495bd30e5cacba  data/codebench/archives/cb_dataset_2017_2_v1.81.tar.gz
6141ecad9e93b58c981a0e47397811aae946f00b0b3dd9d2173d861280506790  data/codebench/archives/cb_dataset_2018_1_v1.81.tar.gz
aa358355a2189a7d5d658c8a8e602d60cf83e0c85ccd9b04dda6154715630abe  data/codebench/archives/cb_dataset_2018_2_v1.81.tar.gz
380ddb6c6efde0c329eed1ac6b2867fddee4a148883ce8e096673a2f4608ab2e  data/codebench/archives/cb_dataset_2019_1_v1.81.tar.gz
f379ea6f89d4b8385559464eae0c2858458b1408b553da8ba05b6bf3244166c3  data/codebench/archives/cb_dataset_2019_2_v1.81.tar.gz
803ebbba0b8591b17fc58fd257b567f810d64f9d64539a261b77c48b2fbcfe15  data/codebench/archives/cb_dataset_2020_1_v1.81.tar.gz
d95496145723add329175dea733ebf75578c30aebfab2607082a6edb6ceabde8  data/codebench/archives/cb_dataset_2020_2_v1.81.tar.gz
ece809c53c343293b9020d5b01ee46773b8d5e014df195681c9a016d56516743  data/codebench/archives/cb_dataset_2020_ERE_v1.81.tar.gz
42f8d77f0ddcc65a584289e418d4814b8b00b9e58e1b69853efd891a8e346f37  data/codebench/archives/cb_dataset_2021_1_v1.81.tar.gz
6915a5bd2f11a002b4217190c1f0a082ffd4e87cc1114c32f37c2b6ec83546bf  data/codebench/archives/cb_dataset_2021_2_v1.81.tar.gz
592c5768bc21318e5ad05ee29de3a980d9c2e2766b988fc56cc3ee03b4fe9958  data/codebench/archives/cb_dataset_2022_1_v1.81.tar.gz
3894fd6888147afed01951f397d54336d925b1f73a9ac8b3defecf3066358d9f  data/codebench/archives/cb_dataset_2022_2_v1.81.tar.gz
925168b9b0d540034e20eeebd0f41aec1e8aef6ddb0aac976d01b02dca71528e  data/codebench/archives/cb_dataset_2023_1_v1.81.tar.gz
933440738082d8d3a2acac5c012c15885d36ddac29d39cd6fcde26e8354303b1  data/codebench/archives/cb_dataset_2023_2_v1.81.tar.gz
ff6b870a5ceef6b9dc6ed076612dc3b16f978bc8e5ed096cb5b8cf16c9b71c62  data/codebench/archives/cb_dataset_2024_1_v1.81.tar.gz
4dd4a1bd5b7df4d4201e343d258d4a76447e11dd3c0c433c1527092002483d58  data/accoding/ACcoding-Dataset-v1.0.0.zip
8cc738fb88ad760571d6f2a23059bfee0ffcae3bcd830514c9cbd5c6d5a046f1  data/assessments.csv
4f16eee7454b15e109b0a21a0e43be820e6846ed6f9301bb7feb5ab5ad737a75  data/courses.csv
fd5320786328d05af841ee7dd4b5871b9dada3b9fe9d6a3642b2f42635510a6e  data/studentAssessment.csv
7e6f3e474a5eee00639d2a414a6c7e928745823c2d2c2563ca1780145f99b0d6  data/studentInfo.csv
0d32676285372aaf2e7a80304e5b274b4fba24313e2ca4c04317225e1ec90170  data/studentRegistration.csv
52668253d876c5becbcb72185977152700cecab2942aca807fecc3dd54b937f0  data/studentVle.csv
d1b28303dea802ad87b4484e1196e878e06824850b9a4fe8aa34693439fe87e9  data/vle.csv
8bb5d1c82e89e467062b6582996232df24edfebadbaf3287a8c985ca178ba92d  data/azure_functions_2021/AzureFunctionsInvocationTraceForTwoWeeksJan2021.rar
848e1a1d22a46c96fdc3868e6e7d510a94d6283e47ad47ee380008cc7a7a0fbd  data/intel_netbatch_2012/Intel-NetbatchD-2012-1.swf.gz
2fc37df5cc14c355fc7a88235f72e54fdf5f0d93de09399d015383ee5c35a59d  evidence/lpc_egee/raw/LPC-EGEE-2004-1.2-cln.swf.gz
```

## What the pipeline writes here

Everything else under `data/` is derived and rebuilt by the commands in the top-level
README: `data/codebench/parquet/` (`scripts/parse_archive.py`),
`data/derived/codebench_cache_r4/` (`scripts/build_cache.py`),
`data/derived/package_ranking_scores/` (`scripts/fit_scores.py`) and
`data/derived/overlay_traces/` (`scripts/build_overlays.py`). None of it is included:
it is derived row by row from the datasets above.
