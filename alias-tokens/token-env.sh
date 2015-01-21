#!/bin/bash

tokenfile=$1
if [[ -z $tokenfile ]]; then
    echo "USAGE: source token-env.sh tokenfile"
    exit 1
fi
echo "Setting environment variables UTOKEN and PTOKEN"
export UTOKEN=`sed 's/{"alias": \?"\([^"]*\)\".*/\1/' $tokenfile`
export PTOKEN=`sed 's/.*"secret": \?"\([^"]*\)\"}/\1/' $tokenfile`
echo UTOKEN=$UTOKEN
echo PTOKEN=$PTOKEN
