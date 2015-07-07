#!/usr/bin/env python

import os

gridjobs = set(os.environ['GRIDJOBS'].split())
cndajobs = set(os.environ['CNDAJOBS'].split())

if os.access('ignorejobs.txt',os.F_OK):
    with open('ignorejobs.txt') as f:
        ignorejobs = set(f.read().split())
else:
    ignorejobs = set()
# Jobs that are tracked by cnda and by grid
# If we are ignoring these, we can stop
tracked = cndajobs & gridjobs
ignorejobs -= tracked

# Jobs that are tracked by cnda, but not by the grid (and are not ignored)
orphans = cndajobs - tracked - ignorejobs

# Finish: write new ignore list and orphans

with open('ignorejobs.txt','w') as f:
    f.write('\n'.join(ignorejobs))

with open('orphans.txt','w') as f:
    f.write('\n'.join(orphans))

if len(orphans)==0:
    print "Pass"
else:
    import json
    print "Fail"

    with open('full-job-results.json') as f:
        jobResults = json.load(f)
    jobs = jobResults['ResultSet']['Result']
    orphanJobs = [job for job in jobs if job['job_id'] in orphans]
    titles = ['job_id',"workflow_id",'session_label','pipeline_name','status','launch_time','userfullname']
    with open('orphan-details.txt','w') as f:
        f.write(" ".join(titles)+'\n')
        for oj in orphanJobs:
            f.write(" ".join([oj[title] for title in titles])+"\n")
