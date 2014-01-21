#!/usr/bin/python

'''
INPUT ARGS
USER PASSWORD HOST PROJECT SUBJECT_ID SESSION_LABEL ASSESSOR_1_ID "ASSESSOR_1_STATUS" ... ASSESSOR_N_ID "ASSESSOR_N_STATUS"
'''

import sys
import os
import re
import lxml.etree as etree
from datetime import date
from itertools import izip

def pairwise(iterable):
    "s -> (s0,s1), (s2,s3), (s4, s5), ..."
    a = iter(iterable)
    return izip(a, a)

#  READ INPUT
[user,password,host,project,subjectid,sessionlabel] = sys.argv[1:7]
assessorInput = sys.argv[7:]

datetimere = re.compile('\d{14}')

recentAssessor = ''
for (assessId,status) in pairwise(assessorInput):

    if status != '':
        passed = ('Passed' in status) # True if most recent status is "Passed"

    # Test if we are looking at an assessor done more recently than the one currently in the "recentassessors" dict
    assessDate = datetimere.findall(assessId)
    currentRecentAssessDate = datetimere.findall(recentAssessor)
    if assessDate > currentRecentAssessDate:
        recentAssessor = assessId

basedir = os.getcwd()

statusStr = 'Passed'
methodStr = 'Automated'
dateStr = date.today().strftime('%Y-%m-%d')
notesStr = 'Flavin'
if passed:
    existingassessorpath = '%s/assessors/%s.temp'%(basedir,recentAssessor)
    newassessorpath = '%s/assessors/%s.new'%(basedir,recentAssessor)

    # print 'Reading %s'%existingassessorpath
    tree = etree.parse(existingassessorpath)
    root = tree.getroot()

    valid = etree.SubElement(root,'{http://nrg.wustl.edu/xnat}validation',status=statusStr)
    etree.SubElement(valid,'{http://nrg.wustl.edu/xnat}method').text = methodStr
    etree.SubElement(valid,'{http://nrg.wustl.edu/xnat}date').text = dateStr
    etree.SubElement(valid,'{http://nrg.wustl.edu/xnat}notes').text = notesStr

    # # print 'Writing %s'%newassessorpath
    # # print 'This is where I write the new assessor'
    tree.write(newassessorpath)


output = [user,password,host,project,subjectid,sessionlabel,recentAssessor]
print ' '.join(output)

# Run as
# python pet-need-ids-step1.py | xargs -L 1 ./pet-need-ids-step2.sh {user} {password} {host} | xargs -L 1 python pet-need-ids-step3.py | xargs -L 1 ./pet-need-ids-step4.sh | tee -a pet-passed-assessors.txt
