#!/bin/bash

USERTOKEN=$1
PASSTOKEN=$2
DEBUG=$3
OUTFILENAME=$4
LAUNCH_STRING=$5

if [[ "$DEBUG" == "true" ]]
then
    echo DEBUG=$DEBUG
    echo PASSTOKEN=$PASSTOKEN
    echo USERTOKEN=$USERTOKEN
    echo OUTFILENAME=$OUTFILENAME
    echo LAUNCH_STRING=$LAUNCH_STRING
fi

# I should be launched from ~/flavin-fs-relaunch-relaunch
PWD=`pwd`
if [[ ! "$PWD" == "${HOME}/flavin-fs-relaunch-relaunch" ]]
then
    echo Launch me from ${HOME}/flavin-fs-relaunch-relaunch
    exit
fi

# I put new user/password tokens in when I made the new launch strings, but they may have grown stale by the time I run this
FRESH_LAUNCH_STRING=`echo $LAUNCH_STRING | sed -e 's/-u [^ ]*/-u '${USERTOKEN}'/' -e 's/-pwd [^ ]*/-pwd '${PASSTOKEN}'/'`
if [[ "$DEBUG" == "true" ]]
then
    echo ---------------------------------------
    echo Beginning with launch string...
    echo FRESH_LAUNCH_STRING=$FRESH_LAUNCH_STRING
fi

FS_ID=`echo $LAUNCH_STRING | sed 's/.*-id \([^ ]*\).*/\1/'`
FS_DIR=`cat batch1.log | grep $FS_ID | grep Moving | head -1 | sed 's#Moving \([^ ]*\) to .*#\1#'`
MR_LABEL=`echo $FS_DIR | sed 's#.*\/\([^\/]*\)$#\1#'`
# DATESTAMP_DIR=`echo $FS_DIR | sed 's#\/'$MR_LABEL'$##'`
BUILD_DIR=`echo $LAUNCH_STRING | sed 's#.*parameterFile \([^ ]*\)\/Freesurfer_relaunch_params_[0-9]\{8\}\.xml .*#\1#'`
if [[ "$DEBUG" == "true" ]]
then
    echo FS_ID=$FS_ID
    echo FS_DIR=$FS_DIR
    echo MR_LABEL=$MR_LABEL
    echo pushd $BUILD_DIR
fi

pushd $BUILD_DIR

# Logs
BATCH_FILE=`ls logs | grep batch$`
ERR_FILE=`ls logs | grep err$`
LOG_FILE=`ls logs | grep log$`
if [[ "$DEBUG" == "true" ]]
then
    echo BATCH_FILE=$BATCH_FILE
    echo ERR_FILE=$ERR_FILE
    echo LOG_FILE=$LOG_FILE
fi

# Get the files
echo pushd /tmp/flavin-fs/${MR_LABEL}
pushd /tmp/flavin-fs/${MR_LABEL}
echo find mri -name "*mgz"
find mri -name "*mgz"
echo find mri -name "*mgz" -exec cp -r {} ${FS_DIR}/{} \;
if [[ ! "$DEBUG" == "true" ]]
then
    find mri -name "*mgz" -exec cp -r {} ${FS_DIR}/{} \;
fi
echo popd
popd

# Run the missing steps
if [ -a logs/${BATCH_FILE}2 ]
then
    echo "old batch file exists"
    echo "rm logs/${BATCH_FILE}2"
    rm logs/${BATCH_FILE}2
fi
echo "Building batch file of the missing steps"
echo "head -2 logs/$BATCH_FILE > logs/${BATCH_FILE}2"
head -2 logs/$BATCH_FILE > logs/${BATCH_FILE}2
echo "tail -5 logs/$BATCH_FILE >> logs/${BATCH_FILE}2"
tail -5 logs/$BATCH_FILE >> logs/${BATCH_FILE}2
echo "Change the cd to a pushd"
echo "sed 's/^cd /pushd /' logs/${BATCH_FILE}2"
sed 's/^cd /pushd /' logs/${BATCH_FILE}2
echo "echo popd >> logs/${BATCH_FILE}2"
echo popd >> logs/${BATCH_FILE}2
echo ----------
echo "Running the batch file"
echo "source logs/${BATCH_FILE}2 2>> logs/$ERR_FILE 1>> logs/$LOG_FILE"
if [[ ! "$DEBUG" == "true" ]]
then
    source logs/${BATCH_FILE}2 2>> logs/$ERR_FILE 1>> logs/$LOG_FILE
fi

echo "rm logs/${BATCH_FILE}2"
rm logs/${BATCH_FILE}2
echo popd
popd

# Restart pipeline
echo "Writing launch string to file $OUTFILENAME: $FRESH_LAUNCH_STRING"
if [[ ! "$DEBUG" == "true" ]]
then
    echo $FRESH_LAUNCH_STRING >> $OUTFILENAME
    echo
fi
