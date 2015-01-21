import os,sys,json,requests

def get(url,**kwargs):
    try:
        r = requests.get( url, **kwargs )
        r.raise_for_status()
    except (requests.ConnectionError, requests.exceptions.RequestException) as e:
        print "Request Failed"
        print "    " + str( e )
        sys.exit(1)
    return r

host = 'https://cnda.wustl.edu'
auth = (os.environ['UTOKEN'],os.environ['PTOKEN'])
infile = "projects-with-pup.json"


r = get( host+"/data/JSESSION", auth=auth, verify=False )
jsessionID = r.content
print "JSESSION ID: %s" % jsessionID
cookie = {"Cookie": "JSESSIONID=" + jsessionID}

print "Getting list of projects with PUP."
with open(infile,"r") as f:
    projects = json.loads(f.read())
print " ".join(projects)


# r = get( host+"/data/projects?format=json&columns=ID,URI", headers=cookie, verify=False )
# allProjectsList = r.json()["ResultSet"]["Result"]
# print "Got it."

# hasPup = []
print
for proj in projects:
    print "Getting PUP default params for %s" % proj
    r = get( host + "/data/projects/%s/config/pipelines/PETUnifiedPipeline_default_params" % proj, headers=cookie, verify=False)
    defaultParams = json.loads(r.json()["ResultSet"]["Result"][0]["contents"])

    defaultParams["filter"]["default"] = 1
    data = json.dumps(defaultParams)

    print "Putting up default params with filter defaulted to 1"
    r = requests.put( host + "/data/projects/%s/config/pipelines/PETUnifiedPipeline_default_params?inbody=true" % proj, headers=cookie, verify=False, data=data)

print "All done."
