#!/usr/bin/python

import csv
from sys import argv, exit
from os import rename

try:
    label = argv[2]
    status = argv[1]
except:
    exit('Run as:\npython pet-fill.py status label')

tsvinpath = 'pet-relaunch-filled.txt'
tsvoutpath = 'pet-relaunch-filled.txt.temp'
success=False
with open(tsvinpath,'rU') as tsvin:
    with open(tsvoutpath,'w') as tsvout:
        tsvr = csv.reader(tsvin,delimiter='\t')
        tsvw = csv.writer(tsvout,delimiter='\t')
        for row in tsvr:
            rowout = row
            if label == row[0]:
                success=True
                rowout[1] = status

            tsvw.writerow(rowout)

if success:
    if status == '':
        print "Removed status from %s"%label
    else:
        print "Added status '%s' to %s"%(status,label)
else:
    print "Failed to add status '%s' to %s"%(status,label)

rename(tsvoutpath,tsvinpath)
