#!/bin/bash

#ARGS
# USER PASSWORD HOST PROJECT SESSION_LABEL SESSION_REST_PATH ASSESSOR_ID_1 ... ASSESSOR_ID_N
USER=$1
PASSWORD=$2
HOST=$3
PROJECT=$4
SESSION_LABEL=$5
SESSION_REST_PATH=$6
shift 6

# USE SESSION REST PATH TO GET SUBJECT
SUBJECT=`curl -u ${USER}:${PASSWORD} -k -s -X GET ${HOST}${SESSION_REST_PATH} | grep 'xnat:subject_ID' | sed 's/.*>\([^<]*\)<.*/\1/'`
OUTPUT_STRING="$USER $PASSWORD $HOST $PROJECT $SUBJECT ${SESSION_LABEL}"
# echo $OUTPUT_STRING

while [ $# -ne 0 ] ; do
    ASSESSOR_ID=$1
    ASSESSOR_XML=`curl -u ${USER}:${PASSWORD} -k -s -X GET ${HOST}/data/experiments/${ASSESSOR_ID}\?format=xml`
    echo $ASSESSOR_XML > assessors/${ASSESSOR_ID}.temp
    STATUS=`echo $ASSESSOR_XML | grep [^/]xnat:validation | sed 's/.* status=\"\([^\"]*\)\".*/\1/'`
    # echo $ASSESSOR_XML | grep [^/]xnat:validation | sed 's/.* status=\"\([^\"]*\)\".*/\1/'
    # echo "$ASSESSOR_ID \"${STATUS}\""

    OUTPUT_STRING="$OUTPUT_STRING $ASSESSOR_ID \"${STATUS}\""
    shift
done

echo  $OUTPUT_STRING
# Run as
# python pet-need-ids-step1.py | xargs -L 1 ./pet-need-ids-step2.sh {user} {password} {host} | xargs -L 1 python pet-need-ids-step3.py | xargs -L 1 ./pet-need-ids-step4.sh | tee -a pet-passed-assessors.txt