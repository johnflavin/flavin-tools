#!/bin/bash

USER=$1
PASSWORD=$2
HOST=$3
SESSION=$4

echo $SESSION
curl -u ${USER}:${PASSWORD} -k -s -X GET ${HOST}/data/archive/experiments\?label=${SESSION}\*\&format=csv\&columns=URI
# ID_QUERY=`curl -u ${USER}:${PASSWORD} -k -s -X GET ${HOST}/data/archive/experiments\?label=${SESSION}\*\&format=csv\&columns=URI`
# echo $ID_QUERY
# SESSION_XML=`curl -u ${USER}:${PASSWORD} -k -s -X GET ${HOST}/data/archive/experiments/${SESSION}`
# echo -e $SESSION_XML
# ASSESSORS=`echo -e $SESSION_XML | grep 'xnat:assessor ID=.*FSPETTIMECOURSE' | sed 's/<.* ID=\"\([^\"]*\)\".*/\1/'`
# SUBJECT=`echo -e $SESSION_XML | grep 'xnat:subject_ID' | sed 's/>\([^<]*\)<.*/\1/'`

# for assessor in ${ASSESSORS[*]}
# do
#     ASSESSOR_XML=`curl -u ${USER}:${PASSWORD} -k -s -X GET ${HOST}/data/archive/experiments/${SESSION}/assessors/${assessor}\?format=xml`
#     # echo $ASSESSOR_XML > assessors/${assessor}.temp
#     STATUS=`echo $ASSESSOR_XML | grep [^/]xnat:validation | sed 's/.* status=\"\([^\"]*\)\".*/\1/'`
#     # echo $ASSESSOR_XML | grep [^/]xnat:validation | sed 's/.* status=\"\([^\"]*\)\".*/\1/'
#     echo $SESSION $SUBJECT $assessor $STATUS
# done

# Run as:
# grep OK pet-relaunch-filled.txt | cut -f 1 | xargs -L 1 ./pet-qc.sh pettempuser pettemppassword https://cnda.wustl.edu | tee pet-status-list.txt
