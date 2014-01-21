#!/bin/bash

USER=$1
PASSWORD=$2
HOST=$3
SESSION=$4
ASSESSORID=$5

XMLFILE=assessors/${ASSESSORID}.new

PROJECT=`cat $XMLFILE | sed 's/.* project=\"\([^\"]*\)\".*/\1/'`
SUBJECT=`curl -u ${USER}:${PASSWORD} -k -s -X GET ${HOST}/data/archive/experiments/${SESSION} | grep 'xnat:subject_ID' | sed 's/>\([^<]*\)<.*/\1/'`

curl -u ${USER}:${PASSWORD} -k -X PUT -T ${XMLFILE} ${HOST}/data/archive/projects/${PROJECT}/subjects/${SUBJECT}/experiments/${SESSION}/assessors/${ASSESSORID}\?allowDataDeletion=true
echo
# Run as
# python pet-qc.py pet-status-list.txt | xargs ./pet-qc2.sh blank password https://cnda-dev-flavn1.nrg.mir
# or
# python pet-qc.py pet-status-list.txt | xargs ./pet-qc2.sh pettempuser pettemppassword https://cnda.wustl.edu