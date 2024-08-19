#!/bin/sh

eval $(slop -f "X=%x Y=%y W=%w H=%h")

ffmpeg -y -video_size ${W}x${H} -framerate 60 -draw_mouse 0 -f x11grab -i :0.0+${X},${Y} -pix_fmt yuvj420p -f yuv4mpegpipe - \
 | nc localhost 3000
