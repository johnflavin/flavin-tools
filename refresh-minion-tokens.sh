#!/bin/bash

USERTOKENFILE=$1
UTOKEN=`sed 's/ .*//' < ~/flavin-fs/DIANDF/$USERTOKENFILE`
PTOKEN=`sed 's/.* //' < ~/flavin-fs/DIANDF/$USERTOKENFILE`
NEWTOKENSTR=`curl -ks -u $UTOKEN:$PTOKEN https://cnda.wustl.edu/data/services/tokens/issue/$UTOKEN/$PTOKEN`

# echo `sed -e 's/{"alias":"//' -e 's/","secret":"/ /' -e 's/"}//' <<< $NEWTOKENSTR` > ~/flavin-fs/DIANDF/$USERTOKENFILE
echo -n `sed -e 's/{"alias":"//' -e 's/","secret":"/ /' -e 's/"}//' <<< $NEWTOKENSTR`
