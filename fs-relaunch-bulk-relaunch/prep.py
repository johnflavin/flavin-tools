#!/usr/bin/python

usage='''
Launch as "python batch4.py outfile fsAssessorId"
'''
# import os
import sys
# import shutil
import subprocess as sub
from itertools import izip


try:
    outfile = sys.argv[1]
    fsAssessorId = sys.argv[2]
except IndexError:
    sys.exit(usage)

breakLine = '---------------------------------------'
hippoRootPath = '/tmp/flavin-fs'

def pairwise(iterable):
    "s -> (s0,s1), (s2,s3), (s4, s5), ..."
    a = iter(iterable)
    return izip(a, a)

print '\n'+breakLine
print 'Starting with assessor %s'%fsAssessorId

# Get old launch string
queuelogpath = '/data/CNDA/logs/queue/arc-grid-queue.log'
qlog = sub.Popen(['grep',fsAssessorId,queuelogpath],stdout=sub.PIPE)
tailqlog = sub.Popen(['tail','-1'],stdin=qlog.stdout,stdout=sub.PIPE)
oldLaunchString = tailqlog.communicate()[0].strip('\n')
print 'Found launch string'
print oldLaunchString
# '/data/CNDA/pipeline/bin/PipelineJobSubmitter /data/CNDA/pipeline/bin/XnatPipelineLauncher -pipeline Freesurfer/Freesurfer_relaunch.xml -id 040219_vc14286_freesurfer_20110316 -host https://cnda-dev-flavn1.nrg.mir -u c5233e31-2b74-42f9-9432-2a4c24323546 -pwd 1389975988435 -dataType fs:fsData -label 040219_vc14286_freesurfer_20110316 -supressNotification -project ADRCCAP -parameterFile /data/CNDA/build/ADRCCAP/20140117_102628/fsrfer/040219_vc14286_freesurfer_20110316/Freesurfer_relaunch_params_20140117.xml -notify flavinj@mir.wustl.edu -notify cnda-ops@nrg.wustl.edu -parameter mailhost=mail.nrg.wustl.edu -parameter userfullname=J.Flavin -parameter builddir=/data/CNDA/build/ADRCCAP/20140117_102628/fsrfer -parameter xnatserver=CNDA -parameter adminemail=cnda-ops@nrg.wustl.edu -parameter useremail=flavinj@mir.wustl.edu -workFlowPrimaryKey 1057701'
oldLaunchStringList = oldLaunchString.split(' ')
oldLaunchStringList.insert(oldLaunchStringList.index('-supressNotification')+1,'') # Make number of args even; add blank after 'supressNotification'

# Construct new string by...
# * Replacing user/password tokens with new ones (passed to this script as args)
# * Removing duplicate notification addresses
# * Inserting my email to be notified
# * Make 'useremail' my email
# * Make 'userfullname' my name
args = {
    '-u': 'uuuuu',
    '-pwd': 'ppppp',
    '-startAt': 'BATCH_FILE'
}
params = {
    'useremail': 'flavinj@mir.wustl.edu',
    'userfullname': 'J.Flavin',
    'use_datestamp':''
}
notify = ['flavinj@mir.wustl.edu','owenc@mir.wustl.edu','cnda-ops@nrg.wustl.edu']

newLaunchStringList = oldLaunchStringList[:2] # Keep the job submitter & pipeline launcher
for (flag,val) in pairwise(oldLaunchStringList[2:]):
    if flag not in args and flag != '-notify':

        # Get the workdir by removing the filename from the param file path
        if flag == '-parameterFile':
            workdir='/'.join(val.split('/')[:-1])

        if flag == '-parameter':
            [subflag,subvalue] = val.split('=')
            if subflag not in params:
                newLaunchStringList.append(flag)
                newLaunchStringList.append(val)
        else:
            newLaunchStringList.append(flag)
            newLaunchStringList.append(val)

for key in args:
    newLaunchStringList.append(key)
    newLaunchStringList.append(args[key])

for addr in notify:
    newLaunchStringList.append('-notify')
    newLaunchStringList.append(addr)

# Must find datestamp before appending params
# Easiest way is to look in the log at the failed step
# The working directory of the failed step has the datestamp as its top level
# The line containing the working directory is the fifth-from-last
errLogPath = '%s/logs/%s.err'%(workdir,fsAssessorId)
linesBack = '-5'
print 'Looking in error log %s'%errLogPath
errLogTailStr = sub.Popen(['tail',linesBack,errLogPath],stdout=sub.PIPE).communicate()[0]
print 'Found error message:'
print breakLine
print errLogTailStr
print breakLine

errLogTailList = errLogTailStr.split('\n')
for line in errLogTailList:
    if 'WorkDirectory' in line:
        errLogWorkDirLine = line
datestampDir = errLogWorkDirLine.split(' ')[1]
datestamp = datestampDir.split('/')[-1]
params['use_datestamp'] = datestamp
for key in params:
    newLaunchStringList.append('-parameter')
    newLaunchStringList.append(key+'='+params[key])

# Can also use the err log to find the mrLabel
# e.g. 'Executing: mv  040219_vc14286_freesurfer_*/DATA/040219_vc14286  . '
for line in errLogTailList:
    if 'Executing: mv' in line:
        errLogMvLine = line
errLogMvMRDir = errLogMvLine.replace('  ',' ').split(' ')[2]
mrLabel = errLogMvMRDir.split('/')[-1]

##########################################
# Move the files into place
# rm the old dirs
fsDir = '%s/%s'%(datestampDir,mrLabel)
# print 'Moving FS files into place'
# print 'Moving %s to %s/temp'.format(fsDir,mrLabel)
# if not debug:
#     shutil.move(fsDir,'%s/temp'%datestampDir)
# else:
#     print 'This is where I would move the files'
# print 'Moving {0}/temp/ASSESSORS/{1}/DATA/{2} to {0}/{2}'.format(datestampDir,fsAssessorId,mrLabel)
# if not debug:
#     shutil.move('{0}/temp/ASSESSORS/{1}/DATA/{2}'.format(datestampDir,fsAssessorId,mrLabel),fsDir)
# else:
#     print 'This is where I would move the files'
# print 'Removing %s/temp'%datestampDir
# if not debug:
#     shutil.rmtree('%s/temp'%datestampDir)
# else:
#     print 'This is where I would remove the old directories'


# ##################################
# # Move hippocampal segmentation files into place
# # Currently stored in /tmp/flavin-fs/<mrLabel>/mri
# print '\nSomething'
# tempHippoPath = '%s/%s/mri'%(hippoRootPath,mrLabel)
# fsHippoPath = '%s/mri'%fsDir
# print 'Moving files from %s to %s'%(tempHippoPath,fsHippoPath)
# hippoFiles = os.listdir('%s'%tempHippoPath)
# if not debug:
#     for filename in hippoFiles:
#         print "Moving %s"%filename
#         shutil.move('%s/%s'%(tempHippoPath,filename),'%s/%s'%(fsHippoPath,filename))
# else:
#     print 'This is where I would move the files'

########
# Launch job
########
print 'Writing launch string for assessor %s to file %s'%(fsAssessorId,outfile)
print ' '.join(newLaunchStringList)

outstring='''%s
%s
MR label: %s
Work dir: %s
FS dir: %s
Launch string: %s
'''%(breakLine,fsAssessorId,mrLabel,workdir,fsDir,' '.join(newLaunchStringList))
with open(outfile,'a') as f:
    f.write(outstring)