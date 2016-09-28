#!/usr/bin/env python
import json, os, sys, requests, re, warnings
import datetime as dt

versionNumber="2.1"
dateString="20150716_095300"
author="flavin"
progName=os.path.basename(sys.argv[0])
idstring = "$Id: %s,v %s %s %s Exp $"%(progName,versionNumber,dateString,author)

timeFormat = '%Y%m%d_%H%M%S'

hostDict = {"cnda":"https://cnda.wustl.edu/",
            "tip-dev-flavin1":"https://tip-dev-flavin1.nrg.mir/",
            "cnda-dev-flavn1":"https://cnda-dev-flavn1.nrg.mir/"}

#######################################################
# PARSE INPUT ARGS
tokenFile = sys.argv[1]
#######################################################

now = dt.datetime.today()

with open(tokenFile) as f:
    token = json.load(f)

# Only update token if it is older than 1 day
if 'date' in token:
    try:
        past = dt.datetime.strptime(token['date'],timeFormat)
        if dt.timedelta(days=1) > now-past:
            # We do not need to update the token
            print "Token is still fresh."
            sys.exit(0)
    except SystemExit:
        sys.exit(0)
    except:
        pass

# Find host, either from file contents or filename
if 'host' in token:
    host = token['host']
else:
    shortHost = os.path.basename(tokenFile).strip('.json')
    if shortHost and shortHost in hostDict:
        host = hostDict[shortHost]
    else:
        sys.exit("Could not find 'host' as key in token file %s, and could not figure out host from its filename. Exiting.")

# Make sure the host string conforms to my expectations
hostMatch = re.match(r'(?P<http>https?://)?[^/]*(?P<termslash>/)?',host)
if not hostMatch.group('http'):
    host = 'https://'+host
if hostMatch.group('termslash'):
    host = host.rstrip('/')

# Set up the session
s = requests.Session()
s.verify = False

try:
    s.auth = (token['alias'],token['secret'])
except:
    sys.exit("Must have file %s with contents {'alias':USERNAME,'secret':PASSWORD}" % args.tokenFile)

# Check connection
url = host + '/data/JSESSION'
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    r = s.post(url)
if not r.ok:
    errMessage = "Could not connect."
    if r.status_code == 403:
        errMessage += "\nToken has expired. You must update manually."
    else:
        errMessage += "\n" + r.text

    mess = "Status code {}\n{}".format(r.status_code,errMessage)
    print mess
    sys.exit(mess)

# Get a new token
url = host + '/data/services/tokens/issue'
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    r = s.get(url)
token = r.json()
token['date'] = now.strftime(timeFormat)
token['host'] = host

errMessage = ""
if r.status_code == 200:
    with open(tokenFile,'w') as f:
        json.dump(token,f)
    print "Success"
    sys.exit(0)
elif r.status_code == 403:
    errMessage = "Token has expired. You must update manually."
else:
    errMessage = "Something went wrong."
print "ERROR: "+errMessage
sys.exit("Status code {}\n{}".format(r.status_code,errMessage))
