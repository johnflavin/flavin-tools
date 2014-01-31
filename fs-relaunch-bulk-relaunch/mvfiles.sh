#!/bin/bash

if [ "${1}" == "-h" ]; then
    DOHIPPO="true"
    HIPPO_ROOT_DIR=$2
    shift 2
else
    DOHIPPO="false"
fi


PREPFILE=$1
FSID=$2

echo ----------
echo "Started with assessor $FSID"
echo

MRLABEL=`grep -x -A 4 $FSID $PREPFILE | grep "MR label" | sed 's/MR label: //'`
echo "Found MR label $MRLABEL"
echo

WORKDIR=`grep -x -A 4 $FSID $PREPFILE | grep "Work dir" | sed 's/Work dir: //'`
echo "Found Work dir $WORKDIR"
echo

FSDIR=`grep -x -A 4 $FSID $PREPFILE | grep "FS dir" | sed 's/FS dir: //'`
echo "Found FS dir $FSDIR"
echo

# LAUNCH_STRING=`grep -x -A 4 $FSID $PREPFILE | grep "Launch string" | sed 's/Launch string: //'`
# echo "Found launch string $LAUNCH_STRING"
# echo

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

if [ "${DOHIPPO}" == "true" ]; then
    # move hippo seg files
    HIPPO_DIR=`echo HIPPO_ROOT_DIR | sed 's#\/$##'`"/${MRLABEL}/mri"
    echo "Copying hippo files from $HIPPO_DIR to $FSDIR/mri"
    echo "find $HIPPO_DIR -name '*.mgz'"
    find $HIPPO_DIR -name '*.mgz'
    echo "find $HIPPO_DIR -name '*.mgz' -exec cp {} $MRLABEL/mri \;"
    find $HIPPO_DIR -name '*.mgz' -exec cp {} ${MRLABEL}/mri \;
fi

echo "popd"
popd

# echo
# echo "Writing to file $OUTFILE"
# echo "echo $LAUNCH_STRING >> $OUTFILE"
# echo $LAUNCH_STRING >> $OUTFILE
