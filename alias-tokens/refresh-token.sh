#!/bin/bash

source /nrgpackages/scripts/epd-python_setup.sh

host=$1
if [ -z "$host" ]; then
    host=$HOSTNAME
fi
if [ -z "$host" ]; then
    echo "Cannot resolve host"
    echo "Pass host name (which is also token file name) to this script, or set "'$HOSTNAME'" variable"
fi

tokendir=$HOME/flavin-token

if [ ! -e $tokendir/$host.json ]; then
    echo "Cannot find token file"
    echo "Make a token file called $host.json in directory $tokendir containing your alias token json"
fi

echo "Refreshing tokens for $host"

oldtoken=`cat $tokendir/$host.json`
echo "Old token: $oldtoken"
token=`python $tokendir/refresh-token.py $host $oldtoken`
ret="$?"
echo "New token: $token"
if (( $ret > 0 )); then
    echo "refresh-token.py exited with error status $ret"
else
    echo $token > $tokendir/$host.json

    source $tokendir/token-env.sh $tokendir/$host.json

fi
