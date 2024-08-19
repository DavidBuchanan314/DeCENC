#!/bin/sh

# technically we could use a way lower sample rate, to save data, but I want to keep things
# as standard as possible

# 30M means 30s fragments

DB_FILE="test.db"

#ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo -acodec aac -frag_duration 30M -movflags frag_keyframe+empty_moov+default_base_moof -f mp4 - \
# | python3 splice_metadata.py $DB_FILE /dev/stdin /dev/stdout audio


# oh, it works just as well if we don't pretend it's encrypted, anyway

ffmpeg -y -f lavfi -i anullsrc=r=48000:cl=stereo -acodec aac -frag_duration 30M -movflags frag_keyframe+empty_moov+default_base_moof -f mp4 -
