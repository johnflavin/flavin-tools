#!/bin/bash -x

HOST=$1
UTOKEN=$2
PTOKEN=$3

die(){
    echo >&2 "$@"
    exit 1
}


while read line; do
    ./uploadBOLD.sh $HOST $UTOKEN $PTOKEN $line || die "Upload failed for session $line"
done < toProcess.txt
