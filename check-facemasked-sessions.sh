#!/bin/bash

OUTFILE=$1
SESSION=$2

SUBJECT=`sed 's/_.*//' <<< $SESSION`

FACEMASKED_DICOM_LIST=`find /data/CNDA/archive/DIANDF/arc001/$SESSION/SCANS/*/DICOM -type f -name \*dcm \! -name \*$SUBJECT\*`

if [[ -z $FACEMASKED_DICOM_LIST ]]; then
    echo Session $SESSION ok
else
    echo Session $SESSION has facemasked dicoms
    SCANID=`sed -e 's#.*SCANS/##' -e 's#/DICOM.*##' <<< $FACEMASKED_DICOM_LIST | sort -u`
    echo $SESSION $SCANID >> $OUTFILE
fi