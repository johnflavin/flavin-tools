#!/bin/env python

import os, re, requests

infile = 'filtered-53.txt'

workflowIdRe = re.compile(r'-workFlowPrimaryKey (?P<id>\d{7})')
def getWorkflowId(launchstr):
    return workflowIdRe.search(launchstr).group('id')

dateRe = re.compile(r'Freesurfer_5\.3_params_201410(?P<date>\d{2})\.xml')
def getLaunchDate(launchstr):
    return dateRe.search(launchstr).group('date')

with open(infile) as f:
    launchstrs = f.read.splitlines()

toFail = [getWorkflowId(lstr) for lstr in launchstrs if getLaunchDate(lstr) < '21']

sess = requests.Session()
sess.auth = (os.environ['UTOKEN'],os.environ['PTOKEN'])
sess.verify = False
host = 'https://cnda.wustl.edu'
wflowURI = host + '/data/workflows'

failed = []
for wId in toFail:
    r = sess.put(wflowURI+'/%s?wrk:workflowData/status=Failed (Dismissed)'%wId)
    if not r.ok:
        failed.append(wId)

print failed

# Sanity check
# for wId in toFail:
#     print sess.get(wflowURI+'/%s?format=json'%wId).json()['items'][0]['data_fields']['status']
