FreeSurfer Relaunch Relaunch
============================

Workaround for a REST bug in XNAT. Scripts by John Flavin. 2014-01-31

# INTRO
Old MR sessions in CNDA were created with their unique ID equal to their not-guaranteed-unique label. This caused problems, and has subsequently been changed, but the old data remain.

This matter to us because when we try to run our FreeSurfer Relaunch pipeline on these old sessions, the ID=label situation hits a bug in the XNAT REST API. The effect of this bug is that the zipped FreeSurfer files we get from the REST call have the wrong directory structure; this causes the pipeline to choke.

I developed a set of scripts to efficiently work around this bug.

# USAGE
Things you need to have set up before you do this:
* Assign your batch a number `N`. The output files will all be named with that batch number.
* Generate user and password alias tokens from the XNAT pipeline engine. (Right now I do this by launching a job to the SGE, cancelling it, finding the launch string, and copying the tokens. There is likely a better way.) I'll call them `USERTOKEN` and `PASSTOKEN`.
* If your FS files are old enough, they may not have hippocampal segmentation files. You could upload them into the FreeSurfer files before you launch the job. If you did not do that, then you can move them by passing the directory where you've stored them to one of the scripts. I'll call that directory `HIPPO_DIR`; the files should be in the directory `HIPPO_DIR/MR_LABEL/mri` (where the latter two directories are where FreeSurfer would keep them if you've stored them locally).

## BATCHN.IDS
`echo` (or copy or whatever) the FreeSurfer assessor ids of the failed jobs into a file `batchN.ids`, one id per line. The other scripts will run by going through this `.ids` file line-by-line.

## PREP
Run `./prep.batch.sh N USERTOKEN PASSTOKEN`

This will generate three files:
1. `batchN.prepped` — used by the next script
2. `batchN.sourceme` — this gets run in the end to launch the jobs
3. `batchN.prep.log` — a log file

## MOVE FILES
The instructions differ here depending on if you want to move the hippocampal files or not.
* If you already have your hippocampal segmentation files in place, run `./mvfiles.batch.sh N`
* If you need to move the hippocampal segmentation files now, run `./mvfiles.batch.sh -h HIPPO_DIR N`

The script generates one log file: `batchN.mvfiles.log`

## LAUNCH THE JOBS
Run `./launch.batch.sh N`.

Generates a log file: `batchN.log`. And it launches the jobs, which is nice.
