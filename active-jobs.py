import json, os, sys, requests, warnings

host = 'https://cnda.wustl.edu'
tokenFile = os.environ['HOME'] + '/tokens/cnda.json'
jobResultsFile = 'full-job-results.json'
searchId = 'xs1397497056634_1'

s = requests.Session()

try:
    with open(tokenFile) as f:
        token = json.load(f)
    s.auth = (token['alias'],token['secret'])
except:
    sys.exit("Must have file %s with contents {'alias':USERNAME,'secret':PASSWORD}" % tokenFile)

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    r = s.get(host + '/data/search/saved/%s/results?format=json' % searchId)

errMessage = ""
if r.status_code == 200:
    with open(jobResultsFile,'w') as f:
        json.dump(r.json(),f)

    for job in r.json()['ResultSet']['Result']:
        if job.get('job_id'):
            print job['job_id']

    sys.exit(0)
elif r.status_code == 403:
    errMessage = "Token has expired. You must update manually."
else:
    errMessage = "Something went wrong."

sys.exit("Status code {}\n{}".format(r.status_code,errMessage))
