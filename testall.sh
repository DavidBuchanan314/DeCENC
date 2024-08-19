#!/bin/sh

set -uxo pipefail

SRC_FILE=./test_files/bbb_144p_h264_enc.mp4
DST_FILE=./test_files/decrypted_inplace.mp4
SPLICED_FILE=./test_files/spliced.mp4
DB_FILE=test.db
RECORDING_FILE=./test_files/recorded.y4m

init_db() {
	python3 populate_db.py $DB_FILE $SRC_FILE $DST_FILE
}

craft_mp4() {
	#./mp4gen_hevc.sh finite > $SPLICED_FILE
	./mp4gen.sh finite > $SPLICED_FILE
}

screen_record_mp4() {
	# now we need to "screen record" the stream using ffmpeg
	# Note: ffmpeg will give a few errors/warnings (due to random NAL framing errors), but continue regardless

	# -pix_fmt yuvj420p forces mapping onto full colour range (causing clamping of high and low pixel values)
	# This is undesirable in general but it's what happens when you screen-record a real CDM, so we need to be able to deal with it (we have logic to recover the clamped values)

	# we use -vf to add black bars, to simulate a recording of a larger-than-necessary screen region
	# (this tests our logic for locating the relevant region)

	ffmpeg -y -hide_banner -loglevel error \
		-decryption_key "00000000000000000000000000000000" \
		-i $SPLICED_FILE \
		-vf "scale=iw:ih,pad=iw+16:ih+24:(ow-iw)/2:(oh-ih)/2" \
		-pix_fmt yuvj420p \
		$RECORDING_FILE
}

process_recording() {
	python3 -m lib.process_recording /dev/stdin $DB_FILE < $RECORDING_FILE # test pipelining
}

final_decrypt() {
	python3 final_decrypt.py
}


init_db

while true
do
	craft_mp4
	screen_record_mp4
	process_recording

	if [ $? -eq 0 ]; then # it's a bit janky, but process_recording uses zero exit status to signal if we have all the blocks now
		break
	fi
done

final_decrypt

# you might wanna comment this out for larger files because it's surprisingly slow
echo checking for codec errors...
ffmpeg -hide_banner -loglevel error -i $DST_FILE -f null -
