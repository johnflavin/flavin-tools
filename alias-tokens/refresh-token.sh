#!/bin/bash

source /nrgpackages/scripts/epd-python_setup.sh

host=$1
if [ "$host" == "" ]; then
    host=$HOSTNAME
fi
if [ "$host" == "" ]; then
    echo "Cannot resolve host"
    echo "Pass host name (which is also token file name) to this script, or set "'$HOSTNAME'" variable"
    exit 1
fi

tokendir=$HOME/tokens
if [ "`pwd`" != "$tokendir" ]; then
    cd $tokendir
fi

if [ ! -e $host.json ]; then
    echo "Cannot find token file"
    echo "Make a token file called $host.json in directory $tokendir containing your alias token json"
    exit 1
fi

echo "Refreshing tokens for $host"

oldtoken=`cat $host.json`
token=`python refresh-token.py $host $oldtoken`
if (( $? > 0 )); then
    echo $token
    exit 1
fi
echo $token > $host.json

export UTOKEN=`sed 's/{"alias": \?"\([^"]*\)\".*/\1/' <<< $token`
export PTOKEN=`sed 's/.*"secret": \?"\([^"]*\)\"}/\1/' <<< $token`
echo UTOKEN=$UTOKEN
echo PTOKEN=$PTOKEN
