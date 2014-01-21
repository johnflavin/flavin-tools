#!/bin/bash

USERTOKEN=$1
PASSTOKEN=$2

# I should be launched from ~/flavin-fs-relaunch-relaunch
PWD=`pwd`
if [ ! "$PWD"=="${HOME}/flavin-fs-relaunch-relaunch" ]
then
    echo Launch me from ${HOME}/flavin-fs-relaunch-relaunch
fi

NEW_LAUNCH_STRING_FILE=fs-relaunch-relaunch_batch2.launch

# Source FS setup
source freesurfer5_setup.sh

while read LAUNCH_STRING
do
    # I put new user/password tokens in when I made the new launch strings, but they may have grown stale by the time I run this
    echo $LAUNCH_STRING | sed -e 's/-u [^ ]*/-u '${USERTOKEN}'/' -e 's/-pwd [^ ]*/-pwd '${PASSTOKEN}'/'

    FS_ID=`echo $LAUNCH_STRING | sed 's/.*-id \([^ ]*\).*/\1/'`
    FS_DIR=`cat fs-relaunch-relaunch_batch1.log | grep -e $FS_ID | grep Moving | head -1 | sed 's#Moving \([^ ]*\) to .*#\1#'`
    MR_LABEL=`echo $FS_DIR | sed 's#.*\/\([^\/]*\)$#\1#'`
    DATESTAMP_DIR=`echo $FS_DIR | sed 's#\/'$MR_LABEL'$##'`
    BUILD_DIR=`echo $LAUNCH_STRING | sed 's#.*parameterFile \([^ ]*\)\/Freesurfer_relaunch_params_[0-9]\{8\}\.xml .*#\1#'`
    pushd $BUILD_DIR

    # Logs
    BATCH_FILE=`ls logs | grep batch`
    ERR_FILE=`ls logs | grep err`
    LOG_FILE=`ls logs | grep log`

    # Get the files
    # Download to a temp dir
    mkdir temp
    pushd temp
    # Download, unzip
    # move hippo stuff to fs dir - find <wherever the fs files are> -name \*ippo\*mgz -exec mv {} <wherever we want them to go>
    # rm temp dir
    popd
    rm -r temp



    # Run the missing steps
    tail -4 logs/$BATCH_FILE > logs/${BATCH_FILE}2
    source logs/${BATCH_FILE}2 2>> $ERR_FILE 1>> $LOG_FILE
    rm logs/${BATCH_FILE}2

    popd

    # Restart pipeline
    echo executing: $LAUNCH_STRING
    # $LAUNCH_STRING
done < $NEW_LAUNCH_STRING_FILE
