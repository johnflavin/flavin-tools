#!/bin/bash

USERTOKEN=$1
PASSTOKEN=$2
DEBUG=$3
# LAUNCH_STRING=$4

if [ $DEBUG ]
then
    echo DEBUG=$DEBUG
    echo PASSTOKEN=$PASSTOKEN
    echo USERTOKEN=$USERTOKEN
    # echo LAUNCH_STRING=$LAUNCH_STRING
fi

# I should be launched from ~/flavin-fs-relaunch-relaunch
PWD=`pwd`
if [ ! "$PWD"=="${HOME}/flavin-fs-relaunch-relaunch" ]
then
    echo Launch me from ${HOME}/flavin-fs-relaunch-relaunch
    exit
fi

OUTFILENAME=batch2.newlaunch

while read LAUNCH_STRING
do
    ./batch2_single.sh $USERTOKEN $PASSTOKEN $DEBUG $OUTFILENAME "$LAUNCH_STRING"
done < batch2.launch