#!/bin/bash

function anybar { echo -n $1 | nc -4u -w0 localhost ${2:-1738}; }

anybar "white"

die(){
    echo >&2 "$@"
    exit -1
}

cd ~/pstatus
echo "Clearing ~/pstatus"
if [[ -n "$(ls *.txt)" ]]; then
    mv ignorejobs.txt ignorejobs.txt.save
    rm *.txt
    mv ignorejobs.txt.save ignorejobs.txt
fi
if [[ -n "$(ls *.json)" ]]; then
    rm *.json
    touch full-job-results.json
fi

# Refresh token. This will also allow us to quit this script if the token is expired.
echo "Ensuring cnda token is fresh"
~/bin/refresh-token.py ~/tokens/cnda.json 1> /dev/null 2> /dev/null || die "Token is expired. Cannot connect to CNDA."

# Get jobs with running status
echo 'Getting list of "Active" jobs on CNDA'
~/bin/active-jobs.py > cndajobs.txt || die "Cannot check jobs"

# Get list of jobs tracked by SGE
echo "Getting list of jobs from SGE"
ssh -Y jflavi01@cnda-fs01 qstat -u cnda | /usr/local/bin/gtail --lines +3 | cut -f 1 -d " " > gridjobs.txt

echo "Comparing list / preparing results"
STATUS=`python ~/bin/check-jobs.py | tee status.txt`

if [[ "$STATUS" == "Pass" ]]; then
    anybar "black"
elif [[ "$STATUS" == "Fail" ]]; then
    anybar "red"
fi
