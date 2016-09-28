import pandas as pd
import requests
import os
import json
import logging
import requests.packages.urllib3
requests.packages.urllib3.disable_warnings()

logging.basicConfig(level=logging.INFO)

s = requests.Session()
s.verify = False
host = 'https://cnda.wustl.edu'

sessionUrl = host + '/data/experiments/{}'
launchUrl = host + '/data/projects/{}/pipelines/PETUnifiedPipeline/experiments/{}'

filepath = ''
df = pd.read_csv(filepath, index_col=0)


df['mbf_escaped'] = df.mbf.str.replace('(.*)', r'"\1"')
df['rbf_escaped'] = df.rbf.str.replace('(.*)', r'"\1"')
df['modf_escaped'] = '""'

paramNames = [col for col in df.columns if not (col == 'mbf' or col == 'rbf' or col == 'modf')]

dft = df.transpose().reindex(index=paramNames)

for columnIdx in dft.columns:
    paramDict = dict(zip(paramNames, dft.icol(columnIdx)))
    sessionId = paramDict['sessionId']
    logging.info("Launching for session %s", paramDict['sessionLabel'])

    try:
        r = s.get(sessionUrl.format(sessionId), params={'format': 'json'})
        r.raise_for_status()
    except requests.RequestException as e:
        logging.error("Could not get project for session %s.\n%s", sessionId, e.message)
        continue

    sessionJson = r.json()['items'][0]
    project = sessionJson['data_fields']['project']

    try:
        r = s.post(launchUrl.format(project, sessionId), data=paramDict)
        r.raise_for_status()
        logging.info("Done with session %s", paramDict['sessionLabel'])
    except requests.RequestException as e:
        logging.error("Could not launch for session %s.\n%s", sessionId, e.message)
        continue
