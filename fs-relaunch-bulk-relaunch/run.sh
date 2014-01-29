#!/bin/bash

USERTOKEN=$1
PASSTOKEN=$2
INFILE=$3
OUTFILE=$4
FSID=$5

echo ----------
echo "Started with assessor $FSID"
echo

MRLABEL=`grep -x -A 4 $FSID $INFILE | grep "MR label" | sed 's/MR label: //'`
echo "Found MR label $MRLABEL"
echo

WORKDIR=`grep -x -A 4 $FSID $INFILE | grep "Work dir" | sed 's/Work dir: //'`
echo "Found Work dir $WORKDIR"
echo

FSDIR=`grep -x -A 4 $FSID $INFILE | grep "FS dir" | sed 's/FS dir: //'`
echo "Found FS dir $FSDIR"
echo

LAUNCH_STRING_BASE=`grep -x -A 4 $FSID $INFILE | grep "Launch string" | sed 's/Launch string: //'`
echo "Found launch string base $LAUNCH_STRING_BASE"
echo

# MOVING FILES
echo "---------"
echo "pushd $FSDIR/../"
pushd $FSDIR/../
echo

# move fs files from assessor dir
CURRENT_MR_DIR="temp/ASSESSORS/${FSID}/DATA/${MRLABEL}"
echo "Moving FS files from $CURRENT_MR_DIR to $MRLABEL"
echo
mv $MRLABEL temp
mv $CURRENT_MR_DIR $MRLABEL
rm -r temp

# move hippo seg files
HIPPO_TEMP_DIR="/tmp/flavin-fs/${MRLABEL}/mri"
echo "Copying files from $HIPPO_TEMP_DIR to $FSDIR/mri"
echo "find $HIPPO_TEMP_DIR -name '*.mgz'"
find $HIPPO_TEMP_DIR -name '*.mgz'
echo "find $HIPPO_TEMP_DIR -name '*.mgz' -exec cp {} $MRLABEL/mri \;"
find $HIPPO_TEMP_DIR -name '*.mgz' -exec cp {} ${MRLABEL}/mri \;

echo "popd"
popd

LAUNCH_STRING=`echo $LAUNCH_STRING_BASE | sed 's/-u uuuuu/-u '${USERTOKEN}'/' | sed 's/-pwd ppppp/-pwd '${PASSTOKEN}'/'`
echo "New launch string:"
echo $LAUNCH_STRING
echo
echo "Writing to file $OUTFILE"
echo $LAUNCH_STRING >> $OUTFILE
