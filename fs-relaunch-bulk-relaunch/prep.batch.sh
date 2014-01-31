#!/bin/bash

N=$1
USERTOKEN=$2
PASSTOKEN=$3

echo '#!/bin/bash' > batch${N}.sourceme

echo "while read FSID; do python prep.py $USERTOKEN $PASSTOKEN batch${N}.prepped batch${N}.sourceme \$FSID; done < batch${N}.ids | tee -a batch${N}.prep.log" | tee batch${N}.prep.log
while read FSID; do python prep.py $USERTOKEN $PASSTOKEN batch${N}.prepped batch${N}.sourceme $FSID; done < batch${N}.ids | tee -a batch${N}.prep.log

