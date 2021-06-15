#!/bin/bash

conda_build_dir=${1:-build_recipe}
conda_env_name=${2:-$(basename $(pwd))}

reqs_script_str="
from conda_build.metadata import MetaData;

conda_build_dir='$conda_build_dir';
md = MetaData(conda_build_dir);
reqs = md.meta.get('requirements', {});

build_reqs = reqs.get('build', []);
host_reqs = reqs.get('host', []);
run_reqs = reqs.get('run', []);
test_reqs = md.meta.get('test', {}).get('requires', []);

reqs = set(build_reqs + host_reqs + run_reqs + test_reqs);

print(' '.join(reqs))"

reqs=$(echo $reqs_script_str | conda run -n base --no-capture-output python - 2>/dev/null)

conda create -n $conda_env_name -y $reqs


