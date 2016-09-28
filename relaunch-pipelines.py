#!/usr/bin/env python

"""
Relaunch pipelines from the start

Usage:
    relaunch-pipelines.py HOST USER PASSW IDENTIFIER...
    relaunch-pipelines.py --help | --version

Options:
    HOST            XNAT URL (i.e http://localhost/xnat)
    USER            XNAT username
    PASSW           XNAT password
    IDENTIFIER      Some unique string that will identify the pipeline launch.
                    Usually a session ID, session label, or workflow ID.
    --help          Show this help message and exit
    --version       Show version and exit
"""

__version__ = "1"
__author__ = "Flavin"

import os
import re
import sys
import glob
import requests
import warnings
import subprocess
# import pandas as pd
# from docopt import docopt


# Define useful functions
def die_if_failed(request, message='Failed'):
    if not request.ok:
        print message
        print 'url: ' + request.url
        print request.text
        request.raise_for_status
        sys.exit(1)


def reverse_readline(filename, buf_size=8192):
    """a generator that returns the lines of a file in reverse order"""
    with open(filename) as fh:
        segment = None
        offset = 0
        fh.seek(0, os.SEEK_END)
        total_size = remaining_size = fh.tell()
        while remaining_size > 0:
            offset = min(total_size, offset + buf_size)
            fh.seek(-offset, os.SEEK_END)
            buffer = fh.read(min(remaining_size, buf_size))
            remaining_size -= buf_size
            lines = buffer.split('\n')
            # the first line of the buffer is probably not a complete line so
            # we'll save it and append it to the last line of the next buffer
            # we read
            if segment is not None:
                # if the previous chunk starts right from the beginning of line
                # do not concact the segment to the last line of new chunk
                # instead, yield the segment first
                if buffer[-1] is not '\n':
                    lines[-1] += segment
                else:
                    yield segment
            segment = lines[0]
            for index in range(len(lines) - 1, 0, -1):
                if len(lines[index]):
                    yield lines[index]
        yield segment

def grep_queue_log(searchStr):
    searchRe = re.compile(searchStr)
    for qlog in glob.iglob('/data/*/logs/queue/arc-grid-queue.log'):
        for line in reverse_readline(qlog):
            if searchRe.search(line):
                return line.strip()
    return ''

# def grep_queue_log(searchStr):
#     ret = subprocess.check_output(['ssh','jflavi01@cnda-fs01','grep',searchStr,'/data/*/logs/queue/arc-grid-queue.log'])
#     print 'DEBUG grep queue log:\n{}'.format(ret)
#     return ret.rstrip('\n').split('\n')[-1]


# Read the input arguments
# args = docopt(__doc__, version=__version__)
arglist = sys.argv[1:]
if len(arglist) < 4:
    if '--help' in arglist:
        print __doc__
        sys.exit()
    if '--version' in arglist:
        print __version__
        sys.exit()
    sys.exit(__doc__)

args = dict(zip(['--host','--username','--password'],arglist[:3]))
args['IDENTIFIER'] = arglist[3:]

# Create XNAT session
s = requests.Session()
s.verify = False
s.auth = (args['--username'], args['--password'])

# Clean up host
host = args['--host']
m = re.match(r'https?://', host)
if not m:
    host = 'https://' + host
if host[-1] == '/':
    host = host.rstrip('/')

# Check if we can read the queue log. Quit if failed.
if not any([os.access(qlog, os.R_OK) for qlog in glob.iglob('/data/*/logs/queue/arc-grid-queue.log')]):
    print "Cannot find a queue log at /data/*/logs/queue/arc-grid-queue.log"
    print "Cannot search for pipeline launch strings"
    print "Quitting"
    sys.exit(1)

# Compile regexes
builddirRe = re.compile(r'.* -parameterFile ([^ ]*)/([^ ]*.xml) .*')
useremailRe = re.compile(r'.* -parameter useremail=([^ ]*) ')

# aliasRe matches a UUID. See http://stackoverflow.com/a/14166194/1288474
aliasRe = re.compile(r' -u [a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12} ', re.IGNORECASE)
secretRe = re.compile(r' -pwd \d{13} ') # Unix timestamp


# Define a list to hold identifiers we had to skip
skipped = []


# Requests prints a lot of ssh warnings, so surround everything with this
#  warning catch block
with warnings.catch_warnings():
    warnings.simplefilter("ignore")

    # Try to connect, quit if we failed
    print "Connecting to {}".format(host)
    r = s.post(host + '/data/JSESSION')
    die_if_failed(r, "Connecting to {} failed.".format(host))
    print

    # Get user table
    print "Downloading user table"
    r = s.get(host + '/data/users', params={'format': 'json'})
    die_if_failed(r, "Could not download user table")
    try:
        users = r.json().get("ResultSet").get("Result")
    except AttributeError:
        print "Could not read user table"
        sys.exit(1)
    usernameCache = {}
    print "Done\n"

    # Main loop. Go through all the identifiers we were given and relaunch.
    for identifier in args['IDENTIFIER']:
        os.chdir(os.path.expanduser('~'))

        print "Searching for launch string using identifier {}".format(identifier)
        launchstr = grep_queue_log(identifier)
        if launchstr:
            print "LAUNCHSTR\n{}".format(launchstr)

            # Find builddir
            m = builddirRe.match(launchstr)
            if not m:
                print "Could not find builddir from launch string\nSkipping\n"
                skipped.append(identifier)
                continue
            builddir = m.group(1)
            paramfile = m.group(2)
            print "BUILDDIR\n{}".format(builddir)

            # Check builddir
            if not (os.access(builddir, os.R_OK) and os.access(builddir, os.W_OK)):
                print "Could not read/write builddir {}\n".format(builddir)
                skipped.append(identifier)
                continue

            # Find useremail from launchstr, look up username from downloaded user list
            m = useremailRe.match(launchstr)
            if not m:
                print "Could not find user email from launch string\nSkipping\n"
                skipped.append(identifier)
                continue
            useremail = m.group(1)
            print "user email: {}".format(useremail)
            username = ""
            if useremail in usernameCache:
                username = usernameCache[useremail]
            else:
                for user in users:
                    if user["email"] == useremail:
                        username = user["login"]
                        usernameCache[useremail] = username
                        break
            if not username:
                print "Could not find username from email {}\nSkipping\n".format(useremail)
                skipped.append(identifier)
                continue
            print "username: {}".format(username)

            # Get fresh token for user
            r = s.get(host + '/data/services/tokens/issue/user/{}'.format(username))
            if not r.ok:
                print "Could not download alias token for user {}\nSkipping\n".format(username)
                skipped.append(identifier)
                continue
            try:
                token = r.json()
                alias = token['alias']
                secret = token['secret']
            except ValueError, KeyError:
                print "Could not interpret alias token for user {}".format(username)
                print "Raw return from server: {}".format(r.text)
                print "Skipping\n"
                skipped.append(identifier)
                continue
            print "new user token: {} {}".format(alias, secret)

            os.chdir(builddir)

            print "Cleaning builddir"
            for root, dirs, files in os.walk(builddir, topdown=False):
                for name in files:
                    fullname = os.path.join(root, name)
                    if root == builddir and name == paramfile:
                        continue
                    os.remove(fullname)
                for name in dirs:
                    fullname = os.path.join(root, name)
                    if name == builddir:
                        continue
                    if os.path.islink(fullname):
                        os.remove(fullname)
                    else:
                        os.rmdir(fullname)

            print "Done\n$ ls {}".format(builddir)
            print os.listdir(builddir)
            print

            # Swap in new alias/secret for old
            templaunchstr = aliasRe.sub(' -u {} '.format(alias), launchstr)
            newlaunchstr = secretRe.sub(' -pwd {} '.format(secret), templaunchstr)

            # execute launchstr
            print "Executing launchstr {}".format(newlaunchstr)
            retcode = subprocess.call(newlaunchstr.split())
            if retcode > 0:
                print "Something went wrong. Return code = {}".format(retcode)
                skipped.append(identifier)
                continue

            print "Done\n"
        else:
            print "Could not find a launch string in arc-grid-queue.log using identifier {}\nSkipping\n".format(identifier)
            skipped.append(identifier)
            continue

print "All done\n"
if skipped:
    print "List of identifiers I had to skip:"
    for identifier in skipped:
        print identifier