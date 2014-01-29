#!/bin/bash

USERTOKEN=$1
PASSTOKEN=$2
OLD_LAUNCH_STRINGS_FILE=$3
NEW_LAUNCH_STRINGS_FILE=$4

echo "Reading file $OLD_LAUNCH_STRINGS_FILE"

while read LAUNCH_STRING
do
echo ----------
echo

FSID=`echo $LAUNCH_STRING | sed 's#.* -id \([^ ]*\) .*#\1#'`
echo "Found fsid $FSID"
echo

WORKDIR=`echo $LAUNCH_STRING | sed 's#.* -parameterFile \(.*\)\/Freesurfer_relaunch_params.*#\1#'`
echo "Found workdir $WORKDIR"
echo

echo "Copying old assessor to logs dir"
echo "cp assessors/${FSID}.xml.old $WORKDIR/logs"
cp assessors/${FSID}.xml.old $WORKDIR/logs
echo

echo "Modifying old launch string:"
echo $LAUNCH_STRING
echo

NEW_LAUNCH_STRING=`echo $LAUNCH_STRING | sed 's/\(.* -u \)[^ ]*\( .*\)/\1'${USERTOKEN}'\2/' | sed 's/\(.* -pwd \)[^ ]*\( .*\)/\1'${PASSTOKEN}'\2/' | sed 's/CLEANUP/Zip1/'`

echo "New launch string:"
echo $NEW_LAUNCH_STRING
echo
echo "Writing to file $NEW_LAUNCH_STRINGS_FILE"
echo $NEW_LAUNCH_STRING >> $NEW_LAUNCH_STRINGS_FILE

done < $OLD_LAUNCH_STRINGS_FILE
