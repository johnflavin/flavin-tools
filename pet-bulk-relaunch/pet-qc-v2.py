#!/usr/bin/python

'''
UPDATE ASSESSOR QC Status
Read in filename from stdin. File is many lines formatted as
SubjectId AssessorId [Status]
example:
...
PIB439 PIB439_FSPETTIMECOURSE_20120606101239 Failed-needs reprocessing
PIB439 PIB439_FSPETTIMECOURSE_20120627021842 Passed
PIB439 PIB439_FSPETTIMECOURSE_20131126032119
...
'''

import sys
import os
import re
import lxml.etree as etree
from datetime import date

#  READ FILE
try:
    filename = sys.argv[1]
except:
    sys.exit("Run python pet-qc.py pet-status-list.txt")

datetimere = re.compile('\d{14}')

recentassessors = {}
passed = {}
with open(filename,'r') as f:
    for line in f:
        info = line.strip('\n').split(' ')
        subjid = info[0]
        assessid = info[1]
        if len(info)>2:
            status = ' '.join(info[2:])
            passed[subjid] = ('Passed' in status) # True if most recent status is "Passed"

        try:
            currentassessid = recentassessors[subjid]
            assessdate = datetimere.findall(assessid)
            currentassessdate = datetimere.findall(currentassessid)
            if assessdate > currentassessdate:
                recentassessors[subjid] = assessid
        except KeyError:
            recentassessors[subjid] = assessid

basedir = os.getcwd()

for subjid in passed:
    if passed[subjid]:
        existingassessorpath = '%s/assessors/%s.temp'%(basedir,recentassessors[subjid])
        newassessorpath = '%s/assessors/%s.new'%(basedir,recentassessors[subjid])

        # print 'Reading %s'%existingassessorpath
        tree = etree.parse(existingassessorpath)
        root = tree.getroot()

        valid = etree.SubElement(root,'{http://nrg.wustl.edu/xnat}validation',status="Passed")
        etree.SubElement(valid,'{http://nrg.wustl.edu/xnat}method').text='Automated'
        etree.SubElement(valid,'{http://nrg.wustl.edu/xnat}date').text = date.today().strftime('%Y-%m-%d')
        etree.SubElement(valid,'{http://nrg.wustl.edu/xnat}notes').text='Flavin'

        # print 'Writing %s'%newassessorpath
        # print 'This is where I write the new assessor'
        tree.write(newassessorpath)

        print '%s %s'%(subjid,recentassessors[subjid])