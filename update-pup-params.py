import os,sys,requests

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
auth = (os.environ['UTOKEN'],osenviron['PTOKEN'])

r = get( host+"/data/JSESSION", auth=auth, verify=False )
jsessionID = r.content
print "JSESSION ID: %s" % jsessionID
cookie = {"Cookie": "JSESSIONID=" + jsessionID}


