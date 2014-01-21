#!/bin/bash

USER=$1
PASSWORD=$2
HOST=$3
PROJECT=$4
SUBJECT=$5
SESSION=$6
ASSESSORID=$7

XMLFILE=assessors/${ASSESSORID}.new

echo $SESSION
curl -u ${USER}:${PASSWORD} -k -X PUT -T ${XMLFILE} ${HOST}/data/archive/projects/${PROJECT}/subjects/${SUBJECT}/experiments/${SESSION}/assessors/${ASSESSORID}\?allowDataDeletion=true
echo
# echo $ASSESSORID

# Run as
# python pet-need-ids-step1.py | xargs -L 1 ./pet-need-ids-step2.sh {user} {password} {host} | xargs -L 1 python pet-need-ids-step3.py | xargs -L 1 ./pet-need-ids-step4.sh | tee -a pet-passed-assessors.txt
