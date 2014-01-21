#!/usr/bin/python

import sys
import os
import shutil
import re
from datetime import datetime as dt
from itertools import izip
import subprocess as sub


def pairwise(iterable):
    "s -> (s0,s1), (s2,s3), (s4, s5), ..."
    a = iter(iterable)
    return izip(a, a)

subj = sys.argv[1]

print '**********'
print subj

oldlaunchstrlist = sys.argv[2:]
oldlaunchstrlist = [launchstr.replace('\r','').replace('\n','') for launchstr in oldlaunchstrlist]
newlaunchstrlist = oldlaunchstrlist[:2]

i = oldlaunchstrlist.index('-supressNotification')
oldlaunchstrlist.insert(i+1,'')

for flag,value in pairwise(oldlaunchstrlist[2:]):
    if 'parameterFile' in flag:
        oldparamfilepath = value
    elif 'builddir' in value:
        oldbuilddirpath = value.split('=')[1]
    else:
        newlaunchstrlist.append(flag)
        newlaunchstrlist.append(value)

datetimestring=re.compile('\d{8}_\d{6}')
datestring=re.compile('\d{8}')

now = dt.now()
newbuilddirpath = now.strftime('%Y%m%d_%H%M%S').join(datetimestring.split(oldbuilddirpath))
newparamfilepath = now.strftime('%Y%m%d').join(datestring.split(oldparamfilepath))
newparamfilepath = now.strftime('%Y%m%d_%H%M%S').join(datetimestring.split(newparamfilepath))

if not os.access(oldparamfilepath,os.F_OK):
    sub.call(['python','pet-fill.py','NA',subj])
    # print 'This is where I would pet-fill \'NA\' to subject %s'%subj
    sys.exit()

# Create the new working directory
i = newparamfilepath.rfind('/')
print 'Making directory %s' % newparamfilepath[:i]
os.makedirs(newparamfilepath[:i])
# print 'This is where I would make the directory'

print 'Copying param file from %s to %s'%(oldparamfilepath,newparamfilepath)
shutil.copyfile(oldparamfilepath,newparamfilepath)
# print 'This is where I would write the param file'

newlaunchstrlist.append('-parameterFile')
newlaunchstrlist.append(newparamfilepath)
newlaunchstrlist.append('-parameter')
newlaunchstrlist.append('builddir='+newbuilddirpath)

# sub.call(newlaunchstrlist)
print 'This is where I would launch \'%s\''%' '.join(newlaunchstrlist)
