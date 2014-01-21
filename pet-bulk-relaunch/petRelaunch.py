#!/usr/bin/python

'''
csv file
PET Label   PET Date    PET Project PET Subject Tracer      PET Notes   FS PET TC Date  FS PET TC QC Status FS PET TC QC Note   MR Used for Processing  MR_Proc Subject MR_Proc Date    FS Date     FS QC Status
0           1           2           3           4           5           6               7                   8                   9                       10              11              12          13
example launch string list
['/data/CNDA/pipeline/bin/PipelineJobSubmitter', '/data/CNDA/pipeline/bin/XnatPipelineLauncher', '-pipeline', 'pet/DIAN_Pet.xml', '-id', 'CNDA_E16532', '-label', '0078744_v00_pib', '-host', 'https://cnda.wustl.edu', '-supressNotification', '-u', 'jchristensen', '-dataType', 'xnat:petSessionData', '-project', 'DIAN_952', '-parameterFile', '/data/nil-bluearc/marcus/CNDA_ACCESSORIES/build/DIAN_952/20111209_162040/pet/0078744_v00_pib/DIAN_Pet_params_20111209.xml', '-notify', 'jon@npg.wustl.edu', '-notify', 'cnda-ops@nrg.wustl.edu', '-notify', 'jon@npg.wustl.edu', '-parameter', 'xnat_id=CNDA_E16532', '-parameter', 'cachepath=/data/nil-bluearc/marcus/CNDA_ACCESSORIES/cache/DIAN_952/', '-parameter', 'userfullname=J.Christensen', '-parameter', 'useremail=jon@npg.wustl.edu', '-parameter', 'archivedir=/data/nil-bluearc/marcus/CNDA/DIAN_952/arc001', '-parameter', 'xnatserver=CNDA', '-parameter', 'mailhost=mail.nrg.wustl.edu', '-parameter', 'project=DIAN_952', '-parameter', 'builddir=/data/nil-bluearc/marcus/CNDA_ACCESSORIES/build/DIAN_952/20111209_162040/pet', '-parameter', 'adminemail=cnda-ops@nrg.wustl.edu', '-pwd', '5316bb4fdbee41c8b3bcb44433be85a60ce187d28fe8cabe5b1fe633f94f08c1']
old: /data/CNDA/build/DIAN_952/20111209_162040/pet/0078744_v00_pib/DIAN_Pet_params_20111209.xml
new: /data/CNDA/build/DIAN_952/20131120_162915/pet/0078744_v00_pib/DIAN_Pet_params_20131120.xml
'''


import csv
import subprocess as sub
import os
import re
from datetime import datetime as dt
from itertools import izip
import lxml.etree as etree

def pairwise(iterable):
    "s -> (s0,s1), (s2,s3), (s4, s5), ..."
    a = iter(iterable)
    return izip(a, a)

def updatePath(path):
    return path.replace('/nil-bluearc/marcus','').replace('_ACCESSORIES','')

now = dt.now()
basedir = os.environ['HOME']+'/flavin-pet/'
# logdir = basedir+'logs/%s/'%now.strftime('%Y%m%d_%H%M%S')
logdir = basedir+'logs/'
# os.makedirs(logdir)
csvfilepath = basedir+'petlist.csv'
queuelogpath = '/data/CNDA/logs/queue/arc-grid-queue.log'
oldlaunchstringfilepath = logdir+'pet_oldlaunchstrings.txt'
newlaunchstringfilepath = logdir+'pet_newlaunchstrings.txt'
oldlaunchstringfilepath_failedfile = logdir+'pet_oldlaunchstrings_failedfile.txt'
if os.access(oldlaunchstringfilepath_failedfile,os.F_OK):
    os.remove(oldlaunchstringfilepath_failedfile)

###################################################################
# Old Launch Strings
# Parse the spreadsheet of pipelines to rerun
# Search the queue log for the launch strings used to launch them
# Save out the list of old launch strings
###################################################################
petlabel = []
with open(csvfilepath,'rU') as csvfile:
    petlist = csv.reader(csvfile)
    for row in petlist:
        petlabel.append(row[0])
petlabel.pop(0) # First row is header
paddedlabel = [' %s '%label for label in petlabel]

oldPipelineLaunchStrs = {}
logfile = open(queuelogpath,'r')
oldstrfile = open(oldlaunchstringfilepath,'w')
for line in logfile:
    if 'DIAN_Pet.xml' in line and 'flavinj@mir.wustl.edu' not in line:
        for padlabel,label in zip(paddedlabel,petlabel):
            if padlabel in line: # Fixes error where numeric labels could be found in timestamps
                if label in oldPipelineLaunchStrs:
                    oldstrfile.write(label+' no longer assigned to launch string '+ oldPipelineLaunchStrs[label]+'\n')

                oldPipelineLaunchStrs[label] = line[:-1]
                oldstrfile.write(label+': '+oldPipelineLaunchStrs[label]+'\n**********\n')
oldstrfile.close()
logfile.close()

###################################################################
# New Launch Strings / Build dir / Param file
# Loop over old launch strings
#   Parse the launch string
#   Replace those args that need replacing (host, email, etc.)
#   Create a new build directory (and work directory under that)
#   Copy old param file to new build dir
#   Replace fwhm value: 0.6 -> 6
#   Add build dir and param file paths to launch string
#   Save out list of new launch strings
#   Launch pipeline
###################################################################
args = {
    '-host': 'https://cnda.wustl.edu',
    '-u': 'pettempuser',
    '-pwd': 'pettemppassword',
    '-notify': 'flavinj@mir.wustl.edu'
}
params = {
    'useremail': 'flavinj@mir.wustl.edu',
    'userfullname': 'J.Flavin'
}

datetimestring=re.compile('\d{8}_\d{6}')
datestring=re.compile('\d{8}')

newPipelineLaunchStrArgList = []
# oldStr = oldPipelineLaunchStrs[0]
newstrfile = open(newlaunchstringfilepath,'w')
failedfile = open(oldlaunchstringfilepath_failedfile,'w')
num=0
for label in oldPipelineLaunchStrs:
    oldarglist = [l.strip("'") for l in oldPipelineLaunchStrs[label].split(' ')]
    print '**********'
    print 'Old launch string %s' % ' '.join(oldarglist)

    i = oldarglist.index('-supressNotification')
    oldarglist.insert(i+1,'')

    newarglist = []
    newarglist.extend(oldarglist[0:2]) # PipelineJobSubmitter and XnatPipelineLauncher
    for flag,value in pairwise(oldarglist[2:]): #iterate over flag,value pairs
        value = updatePath(value) # Remove bluearc paths
        if flag not in args:
            if flag == '-parameterFile':
                oldparamfilepath = value # We will get the param file path later
            elif flag == '-parameter':
                [subflag,subvalue] = value.split('=')
                if subflag not in params:
                    if subflag=='builddir':
                        oldbuilddirpath = subvalue # We will get the builddir later
                    elif subflag=='archivedir':
                        newarglist.append(flag)
                        if 'CNDA/archive' not in value:
                            value = value.replace('CNDA','CNDA/archive')
                        newarglist.append(value)
                    else:
                        newarglist.append(flag)
                        newarglist.append(value)
            else:
                newarglist.append(flag)
                newarglist.append(value)

    for key in args:
        newarglist.append(key)
        newarglist.append(args[key])

    for key in params:
        newarglist.append('-parameter')
        newarglist.append(key+'='+params[key])

    # Replace the date and time strings in the old builddir and paramfile paths
    # newbuilddirpath,newparamfilepath = buildDirAndParamFile(oldbuilddirpath,oldparamfilepath)
    now = dt.now()
    newbuilddirpath = now.strftime('%Y%m%d_%H%M%S').join(datetimestring.split(oldbuilddirpath))
    newparamfilepath = now.strftime('%Y%m%d').join(datestring.split(oldparamfilepath))
    newparamfilepath = now.strftime('%Y%m%d_%H%M%S').join(datetimestring.split(newparamfilepath))

    # Check if param file exists
    if not os.access(oldparamfilepath,os.F_OK):
        print 'Cannot access param file %s' % oldparamfilepath
        failedfile.write(label+': '+oldPipelineLaunchStrs[label]+'\n**********\n')
        continue

    # Create the new working directory
    i = newparamfilepath.rfind('/')
    print 'Making directory %s' % newparamfilepath[:i]
    os.makedirs(newparamfilepath[:i])
    # print 'This is where I would make the directory'

    # parse the parameter file xml. replace the fwhm
    print 'Reading param file from %s'%oldparamfilepath
    tree = etree.parse(oldparamfilepath)
    root = tree.getroot()
    for param in root:
        if param[0].text=='fwhm':
            param[1][0].text = '6'
    print 'Writing new param file to %s'%newparamfilepath
    tree.write(newparamfilepath)
    # print 'This is where I would write the param file'

    newarglist.append('-parameterFile')
    newarglist.append(newparamfilepath)
    newarglist.append('-parameter')
    newarglist.append('builddir='+newbuilddirpath)
    newPipelineLaunchStrArgList.append(newarglist)

    newstrfile.write(label+': '+' '.join(newarglist)+'\n**********\n')

    ########
    # Launch job
    ########
    num = num+1
    print 'Submitting job %i'%num
    print ' '.join(newarglist)
    sub.call(newarglist)
    # print 'This is where I would submit the job'

newstrfile.close()
failedfile.close()
