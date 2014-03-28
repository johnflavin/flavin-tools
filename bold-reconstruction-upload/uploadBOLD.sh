#!/bin/bash -x

HOST=$1
USERTOKEN=$2
PASSTOKEN=$3
SESSIONID=$4
ARCHIVEPATH=$5

cd $ARCHIVEPATH

dirsToZip=`ls -d */ | grep -E '[0-9]{14}'`
if [ "$dirsToZip" == "" ]; then
    cd ../
    dirsToZip="BOLD/"
fi

zip BOLD.zip -r $dirsToZip

RESTPATH="$HOST/data/archive/experiments/$SESSIONID/resources/BOLD/files"

/data/CNDA/pipeline/xnat-tools/XnatDataClient -u $USERTOKEN -p $PASSTOKEN -m PUT -l BOLD.zip -r "$RESTPATH?extract=true&overwrite=true&content=BOLD"

rm BOLD.zip
