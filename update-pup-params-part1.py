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
outfile = "projects-with-pup.json"

r = get( host+"/data/JSESSION", auth=auth, verify=False )
jsessionID = r.content
print "JSESSION ID: %s" % jsessionID
cookie = {"Cookie": "JSESSIONID=" + jsessionID}

print "Getting list of all projects."
r = get( host+"/data/projects?format=json&columns=ID,URI", headers=cookie, verify=False )
allProjectsList = r.json()["ResultSet"]["Result"]
print "Got it."

hasPup = []
print
print "Checking if projects have PUP."
for projectDict in allProjectsList:
    print "Does project %s have PUP?" % projectDict["ID"]
    try:
        r = requests.get( host+projectDict["URI"]+"/pipelines", headers=cookie, verify=False )
        r.raise_for_status()
    except (requests.ConnectionError, requests.exceptions.RequestException) as e:
        print "Request Failed"
        print "    " + str( e )
        print
        continue
    projPipelinesList = r.json()["ResultSet"]["Result"]
    for pipelinesDict in projPipelinesList:
        if pipelinesDict["Name"] == "PETUnifiedPipeline":
            hasPup.append(projectDict["ID"])

    print "Yep" if projectDict["ID"] in projectDict else "Nope"
    print

print "All done."
print "Writing results to %s" % outfile
with open(outfile,"w") as f:
    f.write(json.dumps(hasPup))
