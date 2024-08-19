#!/bin/sh

set -euxo pipefail

DB_FILE=test.db

if [ "$#" -eq 0 ]; then
	ENDLESS="endless"
else
	ENDLESS=""
fi

Y4MPIPE=$(mktemp -u -t mp4gen_XXXXXXXXXXXXXX.y4m)
mkfifo $Y4MPIPE # hack: x264 detects format from file extension, so we have to use a named pipe
python3 yuvgen.py $DB_FILE $ENDLESS > $Y4MPIPE &

# clean up pipe (this is a hacky race condition, but we delete it after it's been opened at each end - the inode will hang around until EOF)
# if we somehow lose the 1 second race window, the script will fail
# if we get killed before 1s is up, we'll leave a stray tmp file - not the end of the world.
(sleep 1 && rm $Y4MPIPE) &

# the default_base_moof flag is important for the later splice step, it makes things simpler
./x264/x264 --force-pcm -I 0 --input-range pc --output-csp i420 -o /dev/stdout $Y4MPIPE \
 | ffmpeg -y -hide_banner -loglevel error -fflags +genpts -i - -vcodec copy -movflags frag_keyframe+empty_moov+default_base_moof -bsf:v h264_metadata=video_full_range_flag=0 -f mp4 - \
 | python3 splice_metadata.py $DB_FILE /dev/stdin /dev/stdout video
