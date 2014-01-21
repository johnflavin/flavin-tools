#!/usr/bin/python

# import csv
# import os

'''
Subject IDs and stati: pet-relaunch-filled.txt
IDs of assessors that I automatically passed: pet-passed-assessors.txt
All the assessors: 'pet-status-list.txt'
'''

statusFilename = 'pet-relaunch-filled.txt'
passedAssessorFilename = 'pet-passed-assessors.txt'
allAssessorFilename = 'pet-status-list.txt'

with open(passedAssessorFilename,'r') as f:
    assessors = f.read().split('\n')

passedAssessorDict = {}
multiline = False
for line in assessors:
    if not multiline:
        if 'FSPETTIMECOURSE' in line:
            subjid = line.split('_')[0]
            passedAssessorDict[subjid] = line
        else:
            subjid = line
            multiline = True
    else:
        passedAssessorDict[subjid] = line
        multiline = False

# allAssessorDict = {}
# with open(allAssessorFilename,'r') as f:
#     for line in f:
#         info = line.strip('\n').split(' ')
#         subjid = info[0]
#         assessid = info[1]
#         if len(info)>2:
#             status = ' '.join(info[2:])
#         else:
#             status = '-'

#         try:
#             allAssessorDict[subjid].append( (assessid,status) )
#         except KeyError:
#             allAssessorDict[subjid] = [(assessid,status)]

# USE THIS TO GENERATE LIST OF GOOD SESSIONS WITHOUT ASSESSORS
#
# statusDict = {'OKP':[],'OK-':[],'NA':[],'NO':[]}
# with open(statusFilename,'r') as f:
#     for line in f:
#         if 'PET Label' in line:
#             continue
#         info = line.strip('\n').split('\t')
#         subjid = info[0]
#         status = info[1]
#
#         if status == 'OK':
#             try:
#                 assessor = passedAssessorDict[subjid]
#                 statusDict['OKP'].append( (subjid,assessor) )
#             except KeyError:
#                 statusDict['OK-'].append(subjid)
#         else:
#             statusDict[status].append(subjid)
#
# for subj in statusDict['OK-']:
#     print subj

# THAT IS DONE. RESULTS ARE IN pet-need-assessors.txt

statusDict = {'OK':[],'NA':[],'NO':[]}
with open(statusFilename,'r') as f:
    for line in f:
        if 'PET Label' in line:
            continue
        info = line.strip('\n').split('\t')
        subjid = info[0]
        status = info[1]

        statusDict[status].append(subjid)

print 'These sessions were not launched because I could not find the build directory from their prior runs. They should be relaunched by hand.'
print '\n'.join(statusDict['NA'])
print
print 'These sessions were launched but they failed.'
print '\n'.join(statusDict['NO'])
print
print 'These sessions were launched, they succeeded, and the assessor shown was marked "Passed"'
print '\n'.join( '%s,%s'%(subj,passedAssessorDict[subj]) for subj in statusDict['OK'] )