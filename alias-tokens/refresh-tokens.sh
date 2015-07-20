#!/bin/bash

echo ""
echo "`date +'%Y-%m-%d %H:%M:%S'`"
for tokenfile in $(ls $HOME/tokens/*json); do
    echo "Refreshing token from file `basename $tokenfile`"
    ~/bin/refresh-token.py $tokenfile
done
