#!/bin/bash

if [ "${1}" == "-h" ]; then
    HIPPO="$1 $2"
    shift 2
fi

N=$1

echo "while read FSID; do ./mvfiles.sh $HIPPO batch${N}.prepped \$FSID; done < batch${N}.ids | tee -a batch${N}.mvfiles.log" | tee batch${N}.mvfiles.log
while read FSID; do ./mvfiles.sh $HIPPO batch${N}.prepped $FSID; done < batch${N}.ids | tee -a batch${N}.mvfiles.log
