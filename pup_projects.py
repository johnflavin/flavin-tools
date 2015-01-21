"CCIR_00601",
"CCIR_00667",
"CCIR_00675",
"DIAN_005",
"DIAN_010",
"DIAN_011",
"DIAN_024",
"DIAN_035",
"DIAN_036",
"DIAN_037",
"DIAN_094",
"DIAN_941",
"DIAN_950",
"DIAN_951",
"DIAN_952",
"DIAN_953",
"DIAN_954",
"DIAN_955",
"DIANDF",
"NP720",


for proj in projectsWithPUP:
    r = sess.put(host+'/data/projects/%s/config/pipelines/PETUnifiedPipeline_default_params?inbody=true'%proj,data=json.dumps(config))
    if r.ok: print "Project %s ok"%proj
    else: print "Project %s failed"%proj