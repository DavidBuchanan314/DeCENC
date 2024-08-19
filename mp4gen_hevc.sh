#!/bin/sh

set -euxo pipefail

DB_FILE=test.db

if [ "$#" -eq 0 ]; then
	ENDLESS="endless"
else
	ENDLESS=""
fi

# the default_base_moof flag is important for the later splice step, it makes things simpler
python3 yuvgen.py $DB_FILE $ENDLESS \
 | ./kvazaar/src/kvazaar --no-enable-logging --input-file-format y4m -i - --owf 0 -p 1 --pu-depth-intra 2-2 --no-combine-intra-cus -q 0 --lossless --no-wpp -o /dev/stdout \
 | ffmpeg -y -hide_banner -loglevel error -fflags +genpts -i - -vcodec copy -movflags frag_keyframe+empty_moov+default_base_moof -f mp4 - \
 | python3 splice_metadata.py $DB_FILE /dev/stdin /dev/stdout video
