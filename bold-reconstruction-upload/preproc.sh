#!/bin/bash -x

preproc(){
    SESSIONID=$1
    ARCHIVEPATH=$2

    if [ ! -d $ARCHIVEPATH ]; then
        echo Cannot cd to $ARCHIVEPATH
        return 1
    fi
}

touch toProcess.batch5.preproced.txt
while read line; do
    echo Checking line "$line"
    preproc $line
    if (( $? > 0 )); then
        echo $line >> toFix.txt
    else
        echo $line >> toProcess.batch5.preproced.txt
    fi
done < toProcess.batch5.txt
