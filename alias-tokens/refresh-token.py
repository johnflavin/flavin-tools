import json, os, sys, requests, argparse, re

versionNumber="1"
dateString="2014/03/31 10:25:00"
author="flavin"
progName=os.path.basename(sys.argv[0])
idstring = "$Id: %s,v %s %s %s Exp $"%(progName,versionNumber,dateString,author)

#######################################################
# PARSE INPUT ARGS
parser = argparse.ArgumentParser(description='Refresh CNDA alias token')
parser.add_argument('-v', '--version',
                    help='Print version number and exit',
                    action='version',
                    version=versionNumber)
parser.add_argument('--idstring',
                    help='Print id string and exit',
                    action='version',
                    version=idstring)
parser.add_argument('host',
                    help='Host to connect to')
parser.add_argument('tokenJSON',nargs='+',
                    help='Alias token JSON to be refreshed')
args=parser.parse_args()
#######################################################

host = args.host
hostMatch = re.match(r'(?P<http>https?://)?[^/]*(?P<termslash>/)?',host)
if not hostMatch.group('http'):
    host = 'https://'+host
if not hostMatch.group('termslash'):
    host = host + '/'

tokenJSON = ''.join(args.tokenJSON)
token = json.loads(tokenJSON)

url = host + 'data/services/tokens/issue'
r = requests.get(url, auth=(token['alias'],token['secret']), verify=False)

if r.status_code == 200:
    print(json.dumps(r.json()))
    sys.exit(0)
elif r.status_code == 403:
    print("Token has expired. You must update manually.")
else:
    print("Something went wrong.")

sys.exit("Status code {}".format(r.status_code))

