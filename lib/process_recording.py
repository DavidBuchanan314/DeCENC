import io
import os
import sys
import zlib
import sqlite3
import asyncio
import aiofiles
from lib.rangefix import FFMPEG_LUT, RangeFixer
from lib.util import xor_bytes
from yuvgen import DECENC_MAGIC, WIDTH, HEIGHT, MAGIC_PATTERN

# TEMP HACK FOR TESTING
#from Crypto.Cipher import AES
#aes = AES.new(key=bytes.fromhex("00000000000000000000000000000000"), mode=AES.MODE_ECB)

# NB: aiofiles is pretty slow, and it's the perf bottleneck here.
# However, the "real" invocation of this function will read from a socket,
# which is hopefully more efficient.

# hardcoded for 8x5 macroblocks
HEVC_BLOCK_MAPPING = [
	0,  1,  4,  5,  16, 17, 20, 21,
	2,  3,  6,  7,  18, 19, 22, 23,
	8,  9,  12, 13, 24, 25, 28, 29,
	10, 11, 14, 15, 26, 27, 30, 31,
	32, 33, 34, 35, 36, 37, 38, 39,
]

async def process_y4m(con: sqlite3.Connection, y4m, hevc_mode=True) -> bool:
	cur = con.cursor()
	blocks_found_initial = cur.execute("SELECT COUNT(*) FROM aes_blocks WHERE aes_out IS NOT NULL").fetchone()[0]
	#input_filename = sys.argv[1]
	#y4m_length = os.stat(input_filename).st_size
	#y4m = tellable_bufferedreader(io.FileIO(input_filename, "rb"))
	header = await y4m.readline()
	magic, _, params = header[:-1].partition(b" ")
	assert(magic == b"YUV4MPEG2")
	param_map = {p[0]:p[1:] for p in params.decode().split(" ")}
	y4m_width = int(param_map["W"])
	y4m_height = int(param_map["H"])

	y_size = y4m_width * y4m_height
	uv_size = ((y4m_width + 1) // 2) * ((y4m_height + 1) // 2) * 2

	prev_even_idx = None
	prev_even_data = None
	prevframe = None
	y4m_framectr = -1
	while True:
		y4m_framectr += 1
		#if y4m_length:
		#	print(f"\rProcessing recording: {y4m.tell()}/{y4m_length} input file bytes processed ({(100*y4m.tell()/y4m_length):.2f}%)", end="")

		fsz = 6 + y_size + uv_size
		if hasattr(y4m, "readexactly"): # when it's an asyncio.StreamReader
			try:
				frame: bytes = await y4m.readexactly(fsz)
			except asyncio.IncompleteReadError:
				break
		else: # when it's an aiofile
			frame: bytes = await y4m.read(fsz)
			if not frame:
				break # clean EOF

		if len(frame) != fsz: # unexpected EOF
			raise EOFError("broken y4m stream")

		fhdr = frame[:6]

		if fhdr != b"FRAME\n":
			raise ValueError("bad y4m frame magic")

		luma = frame[6:6+y_size]
		#chroma = frame[6+y_size:6+y_size+uv_size] # not used

		try:
			frame_start = luma.index(MAGIC_PATTERN) - y4m_width
			if frame_start < 0:
				raise ValueError()
		except ValueError:
			print(f"INFO: Could not find frame magic at y4m frame {y4m_framectr}. Skipping.")
			continue

		y0, x0 = divmod(frame_start, y4m_width)
		#print()
		#print(y4m_width, y4m_height)
		#print(luma.index(MAGIC_PATTERN), y4m_width)
		#print("xy", x0, y0)

		def fidx(x, y, length, buf=luma):
			idx = (y0+y)*y4m_width+x0+x
			return buf[idx:idx+length]

		# find gradient ramp
		calibration_ramp = b""
		for y in range(15):
			calibration_ramp += fidx(WIDTH-16, HEIGHT-16+y, 16)
		calibration_ramp += b"\xff"*16
		
		#print()
		#print(FFMPEG_LUT)
		#print(calibration_ramp)

		fixer = RangeFixer(calibration_ramp) # TODO: cache this if ramp is same as before?
		#assert(calibration_ramp == FFMPEG_LUT)
		#print(calibration_ramp) # TODO: do something with this!!!

		header_lines = []
		for y in reversed(range(8)):
			header_lines.append(fixer.recover_partial(fidx(0, y, 16)))
		mode, framectr, iv_hi, iv_lo, maskbytes_hi, maskbytes_lo, _, checksum = header_lines
		expected_checksum = DECENC_MAGIC + f"{zlib.crc32(b''.join(header_lines[:-1])):08x}".encode()
		
		if expected_checksum != checksum:
			print(f"INFO: Bad checksum at y4m frame {y4m_framectr}. Skipping.")
			continue
		
		framectr = int(framectr, 16)


		if framectr == prevframe:
			print(f"INFO: Skipping duplicate y4m frame at {y4m_framectr}")
			continue
		prevframe = framectr

		footer_csum = fixer.recover_partial(fidx(WIDTH-16, HEIGHT-1, 16))
		if footer_csum != expected_checksum:
			print(f"INFO: Bad footer checksum at y4m frame {y4m_framectr}. Skipping.")
			continue

		if framectr % 2 == 0: # even frame
			prev_even_idx = framectr
			prev_even_data = luma
			continue
		else:
			if framectr-1 != prev_even_idx:
				print(f"INFO: odd frame idx ({framectr}) does not correspond with last seen even frame ({prev_even_idx}). Skipping y4m frame {y4m_framectr}")
				continue
			# TODO: don't process the same odd frame twice? (hm no I think our existing dupe detection should handle it)


		iv = bytes.fromhex((iv_hi+iv_lo).decode())
		iv_int = int.from_bytes(iv, "big")
		maskbytes = bytes.fromhex((maskbytes_hi+maskbytes_lo).decode())

		leaks = [] # (keystream, iv)
		mb_idx = 0
		for mb_y in range(0, HEIGHT, 16):
			for mb_x in range(0, WIDTH, 16):
				if (mb_x, mb_y) in [(0, 0), (WIDTH-16, HEIGHT-16)]: # skip metadata blocks
					continue
				for y in range(16):
					leak_a = fidx(mb_x, mb_y+y, 16, buf=prev_even_data) # the "real" values
					leak_b = fidx(mb_x, mb_y+y, 16)           # values ^ 0x80
					recovered_leak = fixer.recover_fullrange(leak_a, leak_b)				
					keystream = xor_bytes(recovered_leak, maskbytes)
					
					if hevc_mode:
						iv_bytes = (iv_int + (HEVC_BLOCK_MAPPING[mb_idx + 1] - 1)*16 + y).to_bytes(16, "big")
					else:
						iv_bytes = (iv_int + mb_idx*16 + y).to_bytes(16, "big")

					#assert(aes.encrypt(iv_bytes) == keystream) # test everything worked!!!

					leaks.append((keystream, iv_bytes))
				mb_idx += 1

		cur.executemany("UPDATE aes_blocks SET aes_out=? WHERE aes_in=?", leaks)
		con.commit()

	total_blocks = cur.execute("SELECT COUNT(*) FROM aes_blocks").fetchone()[0]
	blocks_found = cur.execute("SELECT COUNT(*) FROM aes_blocks WHERE aes_out IS NOT NULL").fetchone()[0]
	blocks_left = total_blocks-blocks_found

	print()
	print("SUMMARY:")
	print(f"Found {blocks_found}/{total_blocks} blocks ({blocks_found-blocks_found_initial} new this session)")
	print(f"{blocks_left} blocks left to find ({100*(blocks_left)/total_blocks:.3f}%)")

	return blocks_left == 0

async def main():
	if len(sys.argv) != 3:
		print(f"USAGE: python3 {sys.argv[0]} recording.y4m database.db")
		return

	con = sqlite3.connect(sys.argv[2])

	input_filename = sys.argv[1]
	async with aiofiles.open(input_filename, "rb") as f:
		success = await process_y4m(con, f, hevc_mode=False)
	
	if not success:
		os._exit(1)

if __name__ == "__main__":
	asyncio.run(main())
