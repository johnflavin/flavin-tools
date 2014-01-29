#!/bin/bash

# The aparc stats files of this batch had SurfArea as a field, but that was supposed to be gone with FS 5.1.
# I made new aparac stats files with SurfArea->WhiteSurfArea by running...
# $ while read STATSDIR; do find $STATSDIR -type f -name \*aparc\* -regex '.*stats$' -exec bash -c 'sed "s/ SurfArea/ WhiteSurfArea/" {} > {}.wsa' \; ; done < batch6.prep.statsdirs
# I also made backups of the original stats files just in case.
# Whis script will mv allthe wsa files onto the same-named non-wsa file.
# Run with...
# while read STATSDIR; do ./batch6.mvstats.sh $STATSDIR; done < batch6.prep.statsdirs | tee batch6.mvstats.log

STATSDIR=$1

echo "Moving wsa stats files in $STATSDIR"
echo pushd $STATSDIR
pushd $STATSDIR

echo Listing files to be moved
echo find . -name \*aparc\* -regex '.*stats.wsa$'
find . -name \*aparc\* -regex '.*stats.wsa$'

echo find . -name \*aparc\* -regex '.*stats$' -exec mv {}.wsa {} \;
find . -name \*aparc\* -regex '.*stats$' -exec mv {}.wsa {} \;

popd
