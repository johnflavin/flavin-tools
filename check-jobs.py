#!/usr/bin/env python

import os
import sys

for fpath in ['gridjobs.txt', 'cndajobs.txt', 'full-job-results.json']:
    if not os.path.isfile(fpath):
        sys.exit('Cannot read ' + fpath)
with open('gridjobs.txt') as f:
    gridjobs = set(f.read().splitlines())
with open('cndajobs.txt') as f:
    cndajobsandworkflows = set(f.read().splitlines())

if cndajobsandworkflows:
    cndajobsandworkflowstuples = map(lambda l: l.split('/'), cndajobsandworkflows)
    cndajobs, cndaworkflows = zip(*cndajobsandworkflowstuples)
    cndajobsset = set(cndajobs)
else:
    cndajobs = []
    cndaworkflows = []
    cndajobsset = set()

if os.access('ignorejobs.txt', os.F_OK):
    with open('ignorejobs.txt') as f:
        ignorejobs = set(f.read().split())
else:
    ignorejobs = set()
# Jobs that are tracked by cnda and by grid
# If we are ignoring these, we can stop
tracked = cndajobsset & gridjobs
ignorejobs -= tracked

# Jobs that are tracked by cnda, but not by the grid (and are not ignored)
cndaorphans = cndajobsset - tracked - ignorejobs
if '' in cndaorphans:
    # We will take care of jobs with no ID separately
    cndaorphans.remove('')

gridorphans = tracked - cndajobsset - ignorejobs


with open('ignorejobs.txt', 'w') as f:
    f.write('\n'.join(ignorejobs))

with open('cnda-orphans.txt', 'w') as f:
    f.write('\n'.join(cndaorphans))

with open('grid-orphans.txt', 'w') as f:
    f.write('\n'.join(gridorphans))

if len(cndaorphans)==0 and "" not in cndajobs and len(gridorphans)==0:
    print "Pass"
else:
    import json
    print "Fail"

    with open('full-job-results.json') as f:
        jobResults = json.load(f)
    jobs = jobResults['ResultSet']['Result']

    try:
        f = open('orphan-details.txt', 'w')
        if len(cndaorphans) > 0 or "" in cndajobs:
            if len(gridorphans) > 0:
                f.write("CNDA orphans\n")
            orphanJobs = [job for job in jobs if job['job_id'] in cndaorphans]
            noJobIdJobs = [job for job in jobs if job['workflow_id'] in cndaworkflows and not job['job_id']]
            titles = ["workflow_id", 'job_id', 'session_label', 'pipeline_name', 'status', 'launch_time', 'userfullname']
            f.write(" ".join(titles)+'\n')
            for oj in orphanJobs:
                f.write(" ".join([oj[title] if title in oj else "-" for title in titles]) + "\n")
            for wf in noJobIdJobs:
                f.write(" ".join([wf[title] if wf.get(title) else "-" for title in titles]) + "\n")

        if len(gridorphans) > 0:
            if len(cndaorphans) > 0 or "" in cndajobs:
                f.write("\nSGE orphans\n")
                f.write("job_id\n")
                for jid in gridorphans:
                    f.write(jid + '\n')
    finally:
        f.close()
