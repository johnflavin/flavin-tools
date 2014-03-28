
# import sys
import os, re, sys, argparse

versionNumber="1"
dateString="2014/03/28 12:04:00"
author="flavin"
progName=sys.argv[0].split('/')[-1]
idstring = "$Id: %s,v %s %s %s Exp $"%(progName,versionNumber,dateString,author)

def main():
    #######################################################
    # PARSE INPUT ARGS
    parser = argparse.ArgumentParser(description='Generate timecourse image from PUP .tac files')
    parser.add_argument('-v', '--version',
                        help='Print version number and exit',
                        action='version',
                        version=versionNumber)
    parser.add_argument('--idstring',
                        help='Print id string and exit',
                        action='version',
                        version=idstring)
    parser.add_argument('csv',
                        help='Input CSV file. Columns are session_id,reconstruction_id,path')
    parser.add_argument('out',
                        help='Output text file. Columns are session_id, path. Joined by delim (default=space).')
    parser.add_argument('out_bad',
                        help='Second output text file, for input lines that don\'t quite work. Columns are session_id,reconstruction_id,path.')
    parser.add_argument('-d','--delim',
                        default=' ',
                        help='Output file delimiter')
    args=parser.parse_args()

    csvFilePath = args.csv
    outFilePath = args.out
    outBadFilePath = args.out_bad
    delim = args.delim
    #######################################################

    #######################################################
    # PARSE AND PROCESS CSV FILE
    pathRe = re.compile(r'^(?P<path>/data/CNDA/archive/[^/]*/[^/]*/[^/]*/PROCESSED/BOLD/)(\d{14}/)?$')
    outList = []
    outBadList = []
    with open(csvFilePath,'r') as f:
        lines = f.read().splitlines()

        for l in lines[1:]:
            sessionId,boldId,archivePathRaw = l.split(',')

            archiveMatch = pathRe.match(archivePathRaw)

            if archiveMatch:
                archivePath = archiveMatch.group('path')
                pathAndId = (sessionId,archivePath)
                if pathAndId not in outList:
                    outList.append(pathAndId)
            else:
                outBadList.append(l)

    with open(outFilePath,'w') as f:
        f.write('\n'.join( delim.join(pathAndId) for pathAndId in outList )+'\n')

    with open(outBadFilePath,'w') as f:
        f.write('\n'.join(outBadList)+'\n')

if __name__ == '__main__':
    print idstring
    main()