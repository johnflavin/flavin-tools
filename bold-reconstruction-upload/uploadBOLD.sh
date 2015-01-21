#!/bin/bash -x

HOST=$1
UTOKEN=$2
PTOKEN=$3
BATCHNUM=$4

die(){
    echo >&2 "$@"
    exit 1
}

upload(){
    DATESTAMP=$1

    if [[ -z "`ls`" ]]; then
        echo "Nothing to do in dir $DATESTAMP"
        return 0
    fi

    find . -type f ! -name \*.dcm | zip -@ BOLD.zip

    RESTPATH="${HOST}/data/experiments/${SESSIONID}/resources/BOLD_${DATESTAMP}/files"
    RESTARGS="extract=true&overwrite=true&content=BOLD"
    result=`/data/CNDA/pipeline/xnat-tools/XnatDataClient -u $UTOKEN -p $PTOKEN -m PUT -l BOLD.zip -r "${RESTPATH}?${RESTARGS}"`

    if [ -n "$result" ]; then
        echo $result
        echo $SESSIONID upload failed
        return 1
    fi

    rm BOLD.zip
}

run(){

    SESSIONID=$1
    ARCHIVEPATH=$2

    if [ ! -d $ARCHIVEPATH ]; then
        echo Cannot cd to $ARCHIVEPATH
        return 1
    fi
    pushd $ARCHIVEPATH

    datestampDirs=`ls -d */ | grep -E '[0-9]{14}' | sed 's#/##'`
    if [[ -z "$datestampDirs" ]]; then
        anyfile=`ls *.* | head -1`
        datestamp=`date -r $anyfile +%Y%m%d%H%M%S`

        upload $datestamp
        if (( $? > 0 )); then
            popd
            return 1
        fi
    else
        for ds in $datestampDirs; do
            pushd $ds
            upload $ds
            if (( $? > 0 )); then
                popd
                return 1
            fi
            popd
        done
    fi

    popd
}

i=1
NEXTBATCHNUM=$(($BATCHNUM+1))
while read line; do
    run $line || die "Upload failed for session $line"
    ((i++))

    echo $line >> processed.batch${BATCHNUM}.txt
    tail -n +$i toProcess.batch${BATCHNUM}.preproced.txt > toProcess.batch${NEXTBATCHNUM}.preproced.txt
done < toProcess.batch${BATCHNUM}.preproced.txt
