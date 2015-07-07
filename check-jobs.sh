#!/bin/bash -e

function anybar { echo -n $1 | nc -4u -w0 localhost ${2:-1738}; }

anybar "white"

cd ~/pstatus
if [[ -n "$(ls *.txt)" ]]; then
    rm *.txt
fi
if [[ -n "$(ls *.json)" ]]; then
    rm *.json
fi


# Refresh token
python ~/bin/refresh-token.py https://cnda.wustl.edu ~/cnda.json

# Get jobs with running status
export CNDAJOBS=`python ~/bin/active-jobs.py`

# Get list of jobs tracked by SGE
export GRIDJOBS=`ssh -Y jflavi01@cnda-fs01 qstat -u cnda | /usr/local/bin/gtail --lines +3 | cut -f 1 -d " "`

STATUS=`python ~/bin/check-jobs.py | tee status.txt`

if [[ "$STATUS" == "Pass" ]]; then
    anybar "black"
elif [[ "$STATUS" == "Fail" ]]; then
    anybar "red"
fi
