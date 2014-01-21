#!/usr/bin/python

# PARSE FILE pet-need-assessors.txt
# FORMAT:
# SESSION LABEL
# TITLE LINE
# "ID","XSITYPE","PROJ","REST PATH"
# e.g.
# PIB913
# "ID","xsiType","project","URI"
# "CNDA_E10463","xnat:petSessionData","NP720","/data/experiments/CNDA_E10463"
# "CNDA_E10463_FSPETTIMECOURSE_20120321012306","pet:fspetTimeCourseData","NP720","/data/experiments/CNDA_E10463_FSPETTIMECOURSE_20120321012306"
# "CNDA_E10463_FSPETTIMECOURSE_20130522084647","pet:fspetTimeCourseData","NP720","/data/experiments/CNDA_E10463_FSPETTIMECOURSE_20130522084647"
# "CNDA_E10463_FSPETTIMECOURSE_20131126082035","pet:fspetTimeCourseData","NP720","/data/experiments/CNDA_E10463_FSPETTIMECOURSE_20131126082035"
# "CNDA_E12083","xnat:petSessionData","PetSession_v2","/data/experiments/CNDA_E12083"

rawInfoFilePath = 'pet-need-assessors.txt'
rawDict = {}
skipNext = False
with open(rawInfoFilePath,'r') as f:
    for line in f:
        if skipNext:
            skipNext = False
        elif line[0] != '"':
            sessionLabel = line.strip('\n')
            rawDict[sessionLabel]=[]
            skipNext = True
        elif 'PetSession_v2' in line:
            pass # We do not want anything from this project in our results
        else:
            rawDict[sessionLabel].append(line.strip('\n'))

for (sessionLabel,csvString) in rawDict.iteritems():
    [sessionID,_,sessionProject,sessionRestPath] = [val.strip('"') for val in csvString[0].split(',')]
    output = [sessionProject,sessionLabel,sessionRestPath]

    for line in csvString[1:]:
        [assessorID,assessorXSIType,assessorProject,assessorRestPath] = [val.strip('"') for val in line.split(',')]
        if ('pet:fspetTimeCourseData' not in assessorXSIType):
            print 'Error'
            print 'assessorXSIType: %s'%assessorXSIType
            print line
        elif (sessionProject != assessorProject):
            print 'Error'
            print 'sessionProject %s != assessorProject %s'%(sessionProject,assessorProject)
            print line
        else:
            output.append(assessorID)

    #OUTPUT
    # PROJECT SESSION_LABEL SESSION_REST_PATH ASSESSOR_ID_1 ... ASSESSOR_ID_N
    print ' '.join(output)

# Run as
# python pet-need-ids-step1.py | xargs -L 1 ./pet-need-ids-step2.sh {user} {password} {host} | xargs -L 1 python pet-need-ids-step3.py | xargs -L 1 ./pet-need-ids-step4.sh | tee -a pet-passed-assessors.txt