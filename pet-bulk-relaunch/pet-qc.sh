#!/bin/bash

USER=$1
PASSWORD=$2
HOST=$3
SUBJECT=$4

ASSESSORS=`curl -u ${USER}:${PASSWORD} -k -s -X GET ${HOST}/data/archive/experiments/${SUBJECT} | grep 'xnat:assessor ID=.*FSPETTIMECOURSE' | sed 's/<.* ID=\"\([^\"]*\)\".*/\1/'`

for assessor in ${ASSESSORS[*]}
do
    ASSESSOR_XML=`curl -u ${USER}:${PASSWORD} -k -s -X GET ${HOST}/data/archive/experiments/${SUBJECT}/assessors/${assessor}\?format=xml`
    echo $ASSESSOR_XML > assessors/${assessor}.temp
    STATUS=`echo $ASSESSOR_XML | grep [^/]xnat:validation | sed 's/.* status=\"\([^\"]*\)\".*/\1/'`
    # echo $ASSESSOR_XML | grep [^/]xnat:validation | sed 's/.* status=\"\([^\"]*\)\".*/\1/'
    echo $SUBJECT $assessor $STATUS
done

# Run as:
# grep OK pet-relaunch-filled.txt | cut -f 1 | xargs -L 1 ./pet-qc.sh pettempuser pettemppassword https://cnda.wustl.edu | tee pet-status-list.txt
