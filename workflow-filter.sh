#!/bin/bash

UTOKEN=$1
PTOKEN=$2
LAUNCHSTR=$3

# echo $LAUNCHSTR
# DATE=`sed 's#.*builddir=\(\S*\) .*#\1#' <<< $LAUNCHSTR | sed -e 's#/data/CNDA/build/[^/]*/##' -e 's#_.*##'`
WORKFLOW_ID=`sed 's/.*-workFlowPrimaryKey //' <<< $LAUNCHSTR`

WORKFLOW_XML=`/data/CNDA/pipeline/xnat-tools/XnatDataClient -u $UTOKEN -p $PTOKEN -m GET -r "https://cnda.wustl.edu/data/workflows/$WORKFLOW_ID"`

STATUS=`sed 's/.* status="\([^"]*\)" .*/\1/' <<< $WORKFLOW_XML`
echo $WORKFLOW_ID $STATUS
# while read launchstr; do ./workflow-fail.sh $UTOKEN $PTOKEN "$launchstr"; done < all-53.txt
if [[ $STATUS != "Complete" && $STATUS != "Failed" ]]; then
    echo "Storing launch string"
    echo $LAUNCHSTR >> filtered-53.txt
fi
