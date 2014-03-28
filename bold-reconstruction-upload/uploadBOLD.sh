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

# TESTS ON VM
# DIR: ~/flavin-bold/bold-reconstruction-upload
#
# TEST 1
# head -2 toProcess.txt | xargs -L 1 ./uploadBOLD.sh https://cnda-dev-flavn1.nrg.mir $UTOKEN $PTOKEN > >(tee LOGS/test_20140328_1355.log) 2> >(tee LOGS/test_20140328_1355.err >&2)
# TEST CASES
# 0137-006 /data/CNDA/archive/ChronicMigraine/arc001/0137-006/PROCESSED/BOLD/
# 0137-007 /data/CNDA/archive/ChronicMigraine/arc001/0137-007/PROCESSED/BOLD/
#
# TEST 2
# ./uploadBOLD.sh https://cnda-dev-flavn1.nrg.mir $UTOKEN $PTOKEN 061212_TT0090_01 /data/CNDA/archive/CCNMD/arc001/061212_TT0090_01/PROCESSED/BOLD/ > >(tee LOGS/test_20140328_1412.log) 2> >(tee LOGS/test_20140328_1412.err >&2)
# TEST CASES
# 061212_TT0090_01 /data/CNDA/archive/CCNMD/arc001/061212_TT0090_01/PROCESSED/BOLD/
# TEST RESULT:
# Files were uploaded, but Manage Files cannot display them. Looks like the catalog has the same ID for files in both subdirectories.
