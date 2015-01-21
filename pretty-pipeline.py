from lxml import etree
import sys, re

infile = sys.argv[1]
try:
    with open(infile,'r') as f:
        root=etree.fromstring(f.read())
except:
    sys.exit('USAGE: python '+sys.argv[0]+' /path/to/pipeline.xml')

pipeurl = 'http://nrg.wustl.edu/pipeline'
prefix = '{'+pipeurl+'}'
nsDict = {'p':pipeurl}

indent = '  '
# paramRe = re.compile(r'/Pipeline/parameters/parameter\[name=\'(?P<param>[^\']*)\'\]/values/unique/text\(\)')

def xp(node,path):
    return node.xpath(path,namespaces=nsDict)

def rxp(path):
    return xp(root,path)

# def crawlFunc(s):
#     numFuncs = s.count('(')
#     lowestOpenIndex = 0
#     highestOpenIndex = s.rfind(')')
#     lowestCloseIndex = s.find('(')
#     highestCloseIndex = len(s)-1


#         if 'concat' in openparts[0] and 'concat'==openparts[0][-6:]:
#             closedparts = openparts[1].split(')')


#     args,therest = postfix.split(')')

# functionRe = re.compile(r'(?P<funcname>[^\(]*)\((?P<funcargs>.*)\)')
concatRe = re.compile(r'concat\((?P<contents>.*)\)')
replaceRe = re.compile(r'replace\((?P<contents>[^\)]*)\)')
loopRe = re.compile(r'PIPELINE_LOOPON\((?P<contents>[^\)]*)\)')
def pparam(s):
    ret = s
    ret = ret.strip().strip('^')
    ret = ret.replace("/Pipeline/name/text()","{PIPELINENAME}")
    ret = ret.replace("/Pipeline/outputFileNamePrefix/text()","{OUTPUTFILENAME}")
    ret = ret.replace("/Pipeline/parameters/parameter[name='","{")
    ret = ret.replace("']/values/unique/text()",'}')
    ret = ret.replace("']/values/unique",'(unique)}')
    ret = ret.replace("']/values/list",'(list)}')
    ret = ret.replace("']",'}')

    # replace loops
    m = loopRe.search(ret)
    if m is not None:
        ret = ret.replace(m.group(0),'{'+m.group('contents')+'}')
    m = concatRe.search(ret)
    if m is not None:
        replMatch = replaceRe.search(m.group('contents'))
        if replMatch is not None:
            left,center,right = m.group('contents').partition(replMatch.group(0))
            newLeft = ''.join(s.strip().replace("'",'') for s in left.split(','))
            newRight = ''.join(s.strip().replace("'",'') for s in right.split(','))
            ret = ret.replace(m.group(0),newLeft+center+newRight)
        else:
            ret = ret.replace(m.group(0),''.join(s.strip().replace("'",'') for s in m.group('contents').split(',')))


    return ret

# print infile
# for child in root:
#     if len(child.getchildren()) > 1

# for n in ['name','description']:
#     print n + ': ' + findChild(root,n).text

print rxp('p:name')[0].text
print rxp('p:description')[0].text


print 'version: '+rxp('p:documentation/p:version')[0].text

authors = rxp('p:documentation/p:authors/p:author')
if authors is not None and len(authors)>0:
    print 'authors: '+', '.join(' '.join(xp(a,attr)[0].text for attr in ['p:firstname','p:lastname']) for a in authors)

print 'Input parameters'
for param in rxp('p:documentation/p:input-parameters/p:parameter'):
    desc = xp(param,'p:description')
    print indent+xp(param,'p:name')[0].text + (': '+desc[0].text if len(desc)>0 else '')

    val = xp(param,'p:values/*')[0]
    if val.tag == prefix+'csv':
        print indent+indent+val.text+' (csv)'
    elif val.tag == prefix+'schemalink':
        print indent+indent+val.text+' (schemalink)'


loopvars = rxp('p:loop')
if len(loopvars) > 0:
    print 'Loop variables'
    for loopvar in loopvars:
        attr = loopvar.attrib
        print indent+' '.join(['',attr['id'],pparam(attr['xpath'])])

print 'Calculated parameters'
for param in rxp('p:parameters/p:parameter'):
    desc = xp(param,'p:description')
    print indent+xp(param,'p:name')[0].text + (': '+desc[0].text if len(desc)>0 else '')

    val = xp(param,'p:values/*')[0]
    print indent+indent+pparam(val.text)

print 'Steps'
for step in rxp('p:steps/p:step'):
    attr = step.attrib
    if 'description' in attr:
        print indent+'{}: {}'.format(attr['id'],attr['description'])
    else:
        print indent+attr['id']
    for a in ['workdirectory','precondition']:
        if a in attr:
            print indent+indent+a+'='+pparam(attr[a])

    for resource in xp(step,'p:resource'):
        print indent+indent+'{}/{}'.format(resource.attrib['location'],resource.attrib['name'])

        paramlist = []
        for arg in xp(resource,'p:argument'):
            val = xp(arg,'p:value')
            if len(val)>0:
                paramlist.append('{}={}'.format(arg.attrib['id'],pparam(val[0].text)))
            else:
                paramlist.append(arg.attrib['id'])
        print indent+indent+indent+'; '.join(paramlist)