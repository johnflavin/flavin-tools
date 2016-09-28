import os
import sys
import json
import requests

with open(os.path.expanduser('~/tokens/cnda.json')) as f:
   token=json.load(f)

sess = requests.Session()
sess.verify = False
sess.auth = (token['alias'],token['secret'])

host = 'https://cnda.wustl.edu'
print "Checking connection to {}".format(host)
r = sess.get(host+'/data/JSESSION')
if not r.ok:
   print "ERROR: Could not initiate connection"
   print r.text
   sys.exit(1)

sessions = sys.argv[1:]

for session in sessions:
   print "Starting for session {}".format(session)
r = sess.get(host+'/data/experiments/{}'.format(session),
            params={'format': 'json'})
if not r.ok:
   print "ERROR: Could not GET session {}".format(session)
   print r.text
   print
   continue


try:
   sessionJson = r.json()['items'][0]
except:
   print "Could not interpret results from session {}".format(session)
   print
   continue

project = sessionJson['data_fields']['project']

for child in sessionJson['children']:
   if child.get('field') == 'scans/scan':
       scans = child['items']
       break

with warnings.catch_warnings():
   warnings.simplefilter('ignore')
   for scan in scans:
       print 'Checking resources for scan {}'.format(scan['data_fields']['ID'])
       for child in scan['children']:
           if child['field'] == 'file':
               resources = child['items']
       for resource in resources:
           resourceLabel = resource['data_fields']['label']
           if resourceLabel == 'SNAPSHOTS':
               if project not in resource['data_fields']['URI']:
                   print 'Removing duplicate {} resource from scan {}'.format(resourceLabel, scan['data_fields']['ID'])
                   r = sess.delete(host+'/data/experiments/{}/scans/{}/resources/{}'.format(session, scan['data_fields']['ID'], resource['data_fields']['xnat_abstractresource_id']))
                   print 'Done'
           elif resourceLabel == 'DICOM':
               print 'Removing/re-adding {} resource from scan {}'.format(resourceLabel, scan['data_fields']['ID'])
               r = sess.delete(host+'/data/experiments/{}/scans/{}/resources/{}'.format(session, scan['data_fields']['ID'], resourceLabel))
               r = sess.put(host+'/data/experiments/{}/scans/{}/resources/{}'.format(session, scan['data_fields']['ID'], resourceLabel))
               print 'Done'