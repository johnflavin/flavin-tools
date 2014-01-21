#!/usr/bin/python

import re
import sys

usage='''USAGE:
python flip-md.py filename
'''
try:
    filename = sys.argv[1]
except Exception, e:
    sys.exit(usage)

# underlinestr='={10}'
# titlestr='%s\n%s\n'%(datestr,underlinestr)
# endstr='%s\n\n'%datestr
# titlere=re.compile(titlestr)
# endre=re.compile(endstr)

print 'Reading file %s'%filename
with open(filename,'r') as f:
    instring = f.read()

# Break the file into blocks by date. Date blocks will start and end with the same date.
dateblockstr = r'(\d{4}-\d\d-\d\d)\n={10}\n.*\n\1\n*'
dateblockre = re.compile(dateblockstr,re.DOTALL)
timebreakstr = r'\n(?=##? \d\d:\d\d)'
timebreakre = re.compile(timebreakstr)
timestr = r'##? (\d\d:\d\d)'
timere = re.compile(timestr)

dateblocks = [block.group(0).strip('\n') for block in dateblockre.finditer(instring)]
dateblockdates = [block.group(1) for block in dateblockre.finditer(instring)]

# If the file was constructed by appending newer date blocks at the top, change that.
if dateblockdates[0] > dateblockdates[-1]:
    dateblocks.reverse()

def timeOrder(dateBlock):
    rawtimeblocks = timebreakre.split(dateBlock)
    # timeblocks is a list of the blocks of time in a date entry.
    # First block is the opening date string
    # Last block ends in closing date string
    head = rawtimeblocks[0]
    tail = rawtimeblocks[-1][-10:]

    rawtimeblocks[-1] = rawtimeblocks[-1][:-10]
    timeblocks = [tblock.strip('\n') for tblock in rawtimeblocks[1:]]

    firsttime = timere.match(timeblocks[0])
    lasttime = timere.match(timeblocks[-1])
    if firsttime and lasttime and firsttime.group(0) > lasttime.group(0):
        timeblocks.reverse()

    timeblocks.append(tail)
    return head+'\n'+'\n\n'.join(timeblocks)

# Break each date block into time blocks. Reorder if necessary.
reorderedDateBlocks = [timeOrder(dblock) for dblock in dateblocks]

outstring = '\n\n'.join(reorderedDateBlocks)+'\n'

with open(filename+'.temp','w') as f:
    f.write(outstring)

# I invoke this with:
#   find ~/Dropbox/Work\ Notes -name \*.md -exec python flip-md.py '{}' \;
# There were problems I had to iron out, but once I fixed them I had a bunch of *.md.temp files in my Work Notes directory.
# I kept a copy of the originals with this line:
#   find *.temp | xargs -L 1 echo | sed 's/\(.*\)\.temp/'\''\1'\'' '\''\1.orig'\''/' | xargs -L 1 cp
# Then made the 'temp's the true versions with:
#   find *.temp | xargs -L 1 echo | sed 's/\(.*\)\.temp/'\''&'\'' '\''\1'\''/' | xargs -L 1 mv
