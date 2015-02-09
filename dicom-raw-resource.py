# 080404_tc27024 080402_tc27002 080402_tc27003

# for dir in {1..20}; do mkdir -p SCANS/$dir/DICOM; cp RAW/1.MR.head_DHead.$dir.* SCANS/$dir/DICOM/; done
# gzip -d SCANS/*/DICOM/1.*

r = sess.get(host+'/data/experiments/%s?format=json'%session)

item = r.json()['items'][0]
scans = item['children'][3]['items']

for scan in scans:
    r = sess.delete(host+'/data/experiments/%s/scans/%s/resources/DICOM'%(session,scan['data_fields']['ID']))
    if not r.ok:
        print("Could not delete DICOM for scan "+scan['data_fields']['ID'])
        break
    r = sess.put(host+'/data/experiments/%s/scans/%s/resources/DICOM'%(session,scan['data_fields']['ID']))
    if not r.ok:
        print("Could not put DICOM for scan "+scan['data_fields']['ID'])
        break


workflowRe = re.compile('hidden_fields\[wrk_workflowData_id="(\d+)"\]')
pip = "WebBasedQCImageCreator"

t = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
wrkflow = '<wrk:Workflow data_type="xnat:mrSessionData"  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:wrk="http://nrg.wustl.edu/workflow" ID="%s" ExternalID="%s" status="Queued" pipeline_name="%s" launch_time="%s"/>'%(session,proj,pip,t)
r = sess.put(host+'/data/workflows?req_format=xml&inbody=true',data=wrkflow)
r.raise_for_status()

r = sess.get(host+'/data/services/workflows/%s?display=LATEST&experiment=%s'%(pip,session))
r.raise_for_status()
m = workflowRe.search(r.text)
if m:
    wf= m.group(1)
else:
    print "failed"



bd = '/data/CNDA/build/%s/%s'%(proj,datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
print bd



print '''
/data/CNDA/pipeline/bin/PipelineJobSubmitter /data/CNDA/pipeline/bin/XnatPipelineLauncher -pipeline /data/CNDA/pipeline/catalog/images/WebBasedQCImageCreator.xml -id %s -host https://cnda.wustl.edu -u %s -pwd %s -dataType xnat:mrSessionData -label %s -supressNotification -project %s -notify flavinj@mir.wustl.edu -notify cnda-ops@nrg.wustl.edu -parameter mailhost=mail.nrg.wustl.edu -parameter userfullname=J.Flavin -parameter builddir=%s -parameter xnatserver=CNDA -parameter adminemail=cnda-ops@nrg.wustl.edu -parameter useremail=flavinj@mir.wustl.edu -workFlowPrimaryKey %s
''' % (session,token['alias'],token['secret'],session,proj,bd,wf)