# TODO: add keyid to metadata
# TODO: randomize pattern bytes on each run (but check there are no naughty byte values!)

import sys
import zlib
import sqlite3
import os
from lib.util import xor_bytes

DECENC_MAGIC = b"DeCENC  " # 8 bytes

WIDTH = 128
HEIGHT = 64#+16
FPS = 60
FRAMECOUNT = 128
AES_BLOCKS_PER_FRAME = ((WIDTH*HEIGHT)//16) - 32 # the metadata macroblocks take up 32 potential AES blocks

# random and arbitrary
MAGIC_PATTERN = b'\xff\xff\xff\xff\x00\xff\xff\xff\x00\xff\xff\x00\x00\xff\x00\xff'

assert(WIDTH % 16 == 0)
assert(HEIGHT % 16 == 0)

Y4M_HEADER = f"YUV4MPEG2 W{WIDTH} H{HEIGHT} F{FPS}:1 Ip A1:1 C420jpeg XYSCSS=420JPEG XCOLORRANGE=FULL\n"

def random_nullfree():
	while True:
		rand = os.urandom(16)
		if b"\0" not in rand and b"\x80" not in rand: # inverse needs to be nullfree also!
			return rand

def load_pgm(path):
	f = open(path, "rb")
	magic = f.readline()
	assert(magic == b"P5\n")
	while (meta := f.readline()).startswith(b"#"): pass # consume comments
	width, height = map(int, meta.strip().decode().split(" "))
	while (meta := f.readline()).startswith(b"#"): pass # consume comments
	assert(meta == b"255\n")
	fb = f.read(width * height).replace(b"\x00", b"\x01") # prevent NALU fuckery!
	assert(len(fb) == width * height)
	return width, height, fb

banner_w, banner_h, banner_fb = load_pgm("./misc/scroller.pgm")

def emit_frame(fb, pattern, framectr, iv):

	# prepare metadata bytes (this is an ad-hoc format I just made up)
	# metadata is ASCII to guarantee a) nothing messes with NALs b) it survives limited->full range conversions
	meta_rows = [
		b"cenc"*4, # the mode (could be cbcs if I ever implement that)
		f"{framectr:016x}".encode(),
		iv[:8].hex().encode(),
		iv[8:].hex().encode(),
		pattern[:8].hex().encode(), # the block pattern
		pattern[8:].hex().encode(),
		MAGIC_PATTERN, # a pattern that's easy to scan for, to locate the start of frame
	]
	crchex = f"{zlib.crc32(b''.join(meta_rows)):08x}".encode() # never hurts to have a checksum
	meta_rows.append(DECENC_MAGIC + crchex)

	# write metadata to macroblock 0
	# we write it upside down, to maximize tearing detection (e.g. if the first row tore)
	for i, meta in enumerate(meta_rows[::-1]):
		fb[i*WIDTH:i*WIDTH+16] = meta
	
	# write vanity scroller, just for fun
	offset = (framectr // 4) % (banner_w - 16)
	for i in range(8):
		fb[(i+8)*WIDTH:(i+8)*WIDTH+16] = banner_fb[i*banner_w+offset:i*banner_w+offset+16]

	# duplicate the checksum to final macroblock (detects frame tearing or codec errors)
	fb[WIDTH*HEIGHT-16:WIDTH*HEIGHT] = meta_rows[-1]

	sys.stdout.buffer.write(b"FRAME\n")
	sys.stdout.buffer.write(fb)


def enumerate_remaining_blocks(cur):
	# enumerate all not-yet-decrypted blocks
	# XXX: we assume IVs are sequential. Maybe we should ORDER BY aes_in???
	CHUNK_SIZE = 1000
	start_id = -1
	while True:
		blocks = []
		for block, idx in cur.execute("SELECT aes_in, aes_block_id FROM aes_blocks WHERE aes_out IS NULL AND aes_block_id>? ORDER BY aes_block_id LIMIT ?", (start_id, CHUNK_SIZE)):
			blocks.append(block)
			start_id = idx
		for block in blocks:
			yield block
		if len(blocks) < CHUNK_SIZE:
			break



if __name__ == "__main__":
	sys.stdout.buffer.write(Y4M_HEADER.encode())

	con = sqlite3.connect(sys.argv[1])
	cur = con.cursor()
	#cur.execute("pragma journal_mode=wal")

	endless = len(sys.argv) == 3 and sys.argv[2] == "endless"

	fb_a = bytearray(int(WIDTH*HEIGHT*1.5))
	fb_b = bytearray(int(WIDTH*HEIGHT*1.5))
	
	total_framectr = 0
	while True:
		pattern_a = random_nullfree()
		pattern_b = xor_bytes(pattern_a, b"\x80"*16)
		for i in range(0, WIDTH*HEIGHT, 16): # fill luma channel with repeating pattern (easy to spot in a hexeditor)
			fb_a[i:i+16] = pattern_a
			fb_b[i:i+16] = pattern_b
		for i in range((WIDTH*HEIGHT)//2): # set UV channels to neutral value
			fb_a[WIDTH*HEIGHT + i] = 0x80
			fb_b[WIDTH*HEIGHT + i] = 0x80

		# fill final block with luma calibration gradient
		n = 0
		for y in range(16):
			for x in range(16):
				fb_a[(HEIGHT-16+y)*WIDTH+(WIDTH-16+x)] = n
				fb_b[(HEIGHT-16+y)*WIDTH+(WIDTH-16+x)] = n
				n += 1
			
		# enumerate all not-yet-decrypted blocks
		blocks = enumerate_remaining_blocks(cur)

		next_iv = bytes(16)
		framectr = 0
		while True:
			# find the next block that wasn't already included in our previous frame
			try:
				while True:
					iv = next(blocks)
					if iv >= next_iv:
						break
			except StopIteration:
				break
			#print("emitting frame for IV", iv.hex())
			emit_frame(fb_a, pattern_a, total_framectr+framectr, iv)
			emit_frame(fb_b, pattern_a, total_framectr+framectr+1, iv)
			framectr += 2
			next_iv = (int.from_bytes(iv, "big") + AES_BLOCKS_PER_FRAME).to_bytes(16)
			#break # XXX TESTING

		#break # XXX testing
		if not endless:
			break

		if framectr == 0: # this means we're out of blocks to process, i.e. we're done
			break

		total_framectr += framectr
