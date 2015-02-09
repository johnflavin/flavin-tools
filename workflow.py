
import re, requests, datetime


def createWorkflow( ID, pipeline):
    # Get expt['xsiType'] and expt['project']
    r = sess.get(host+'/data/experiments?ID={}&format=json'.format(ID))
    r.raise_for_status()
    expt = r.json()['ResultSet']['Result'][0]

    now = datetime.datetime.now()

    workflowStr = '<wrk:Workflow xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:wrk="http://nrg.wustl.edu/workflow" ID="{}" ExternalID="{}" data_type="{}" status="Queued" pipeline_name="{}" launch_time="{}"/>'.format(ID,expt['project'],expt['xsiType'],pipeline,now.strftime('%Y-%m-%dT%H:%M:%S'))

    r = sess.put(host+'/data/workflows?req_format=xml&inbody=true',data=workflowStr)
    r.raise_for_status()

    r = sess.get(host+'/data/services/workflows/{}?display=LATEST&experiment={}'.format(pipeline,ID))

    m = re.search('hidden_fields\[wrk_workflowData_id="(\d+)"\]',r.text)
    if m:
        workflowidStr =  m.group(1)
    return workflowidStr

