import json, os, sys, requests, argparse, re
import datetime as dt

versionNumber="2"
dateString="20150408_090100"
author="flavin"
progName=os.path.basename(sys.argv[0])
idstring = "$Id: %s,v %s %s %s Exp $"%(progName,versionNumber,dateString,author)

timeFormat = '%Y%m%d_%H%M%S'

#######################################################
# PARSE INPUT ARGS
parser = argparse.ArgumentParser(description='Refresh CNDA alias token')
parser.add_argument('host',
                    help='Host to connect to')
parser.add_argument('tokenFile',
                    help='Alias token JSON file')
args=parser.parse_args()
#######################################################

now = dt.datetime.today()

host = args.host
hostMatch = re.match(r'(?P<http>https?://)?[^/]*(?P<termslash>/)?',host)
if not hostMatch.group('http'):
    host = 'https://'+host
if not hostMatch.group('termslash'):
    host = host + '/'

s = requests.Session()
s.verify = False

try:
    with open(args.tokenFile) as f:
        token = json.load(f)
    s.auth = (token['alias'],token['secret'])
except:
    sys.exit("Must have file %s with contents {'alias':USERNAME,'secret':PASSWORD}" % args.tokenFile)

# Only update token if it is older than 1 day
if token.get('date'):
    try:
        past = dt.datetime.strptime(token.get('date'),timeFormat)
        if dt.timedelta(days=1) > now-past:
            # We do not need to update the token
            sys.exit(0)
    except:
        pass


url = host + 'data/services/tokens/issue'
r = s.get(url)
token = r.json()
token['date'] = now.strftime(timeFormat)

errMessage = ""
if r.status_code == 200:
    with open(args.tokenFile,'w') as f:
        json.dump(token,f)
    sys.exit(0)
elif r.status_code == 403:
    errMessage = "Token has expired. You must update manually."
else:
    errMessage = "Something went wrong."

sys.exit("Status code {}\n{}".format(r.status_code,errMessage))
