#!/usr/bin/python

import sys, requests, os
from lxml import etree

resturl = sys.argv[1]
pupIDRe = r'CNDA_E\d{5}_PUPTIMECOURSE_\d{14}'
nsDict = {'xnat':'http://nrg.wustl.edu/xnat','pup':'http://nrg.wustl.edu/pup','re':'http://exslt.org/regular-expressions'}

auth = (os.environ['UTOKEN'],os.environ['PTOKEN'])
r = requests.get(resturl+'?format=xml', auth=auth, verify=False)

def getEl(root,childName):
    return root.xpath("pup:"+childName,namespaces=nsDict)[0]

root = etree.fromstring(r.text.encode('ascii'))
hasPup = False
statsGood = False
for pup in root.xpath("//xnat:assessors/xnat:assessor[re:match(@ID,'{}')]".format(pupIDRe),namespaces=nsDict):
    hasPup = True
    rois = pup.xpath("pup:rois/pup:roi",namespaces=nsDict)
    model = getEl(pup,'model')
    if model is not None and model.text=='logan':
        if not any([('NaN' in getEl(roi,'INTC').text or 'INF' in getEl(roi,'INTC').text) for roi in rois]):
            statsGood = True
            break
    suvrFlag = getEl(pup,'suvrFlag')
    if suvrFlag is not None and suvrFlag.text=='1':
        if not any([('NaN' in getEl(roi,'SUVR').text or 'INF' in getEl(roi,'SUVR').text) for roi in rois]):
            statsGood = True
            break
if hasPup and statsGood:
    print 'Good'