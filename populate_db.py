#!/usr/bin/env python3

import sqlite3
import time
import os
from lib.database import init_db
from lib.boxxy import Box, Moov, Schm, Pssh, Moof, Traf, Senc, Tenc

def populate_db(db_path: str, source_path: str, dest_path: str):
	start_time = time.time()
	con = init_db(db_path)
	cur = con.cursor()
	#cur.execute("PRAGMA journal_mode=WAL") # ok maybe this doesn't help lol

	file_length = os.stat(source_path).st_size
	filestream = open(source_path, "rb")

	total_blocks = 0

	parsectx = {}
	while filestream.tell() < file_length:
		print(f"\rDB import progress: {filestream.tell()}/{file_length} file bytes processed ({(100*filestream.tell()/file_length):.2f}%)", end="")
		box = Box.parse(filestream, parsectx)

		if isinstance(box, Moov): # main file metadata
			tenc: Tenc = box.findall(Tenc)[0]
			schm: Schm = box.findall(Schm)[0]
			key_id = tenc.default_KID

			print("\nINFO: saving key_id:", key_id.hex())
			cur.execute("INSERT INTO meta (input_path, output_path, cenc_mode, key_id) VALUES (?, ?, ?, ?)", (source_path, dest_path, schm.scheme_type.decode(), key_id))

			for pssh in box[Pssh]:
				print("INFO: saving a pssh box:", pssh)
				cur.execute("INSERT INTO pssh (pssh_box) VALUES (?)", (bytes(pssh),))
		
		if isinstance(box, Moof):
			try:
				senc = box/Traf/Senc
				for sample in senc.sample_info:
					iv_int = int.from_bytes(sample["iv"].ljust(16, b"\0"), "big")
					if senc.flags & Senc.Flags.use_subsample_encryption:
						cipher_length = sum(ss["encbytes"] for ss in sample["subsamples"])
					else:
						raise Exception("TODO")
					num_blocks = (cipher_length + 15) // 16 # round up
					cipher_blocks = [((iv_int + i).to_bytes(16, "big"),) for i in range(num_blocks)]
					cur.executemany("INSERT INTO aes_blocks (aes_in) VALUES (?)", cipher_blocks)
					total_blocks += num_blocks
			except ZeroDivisionError:
				pass
	
	con.commit()

	print()
	duration = time.time() - start_time
	print(f"Took {duration:.3f}s ({file_length/(1024*1024)/duration:.1f}MiB/s)")
	print(f"Loaded {total_blocks} AES blocks into db ({total_blocks*16//(1024*1024)}MiB)")
	print("(Note: on-disk db size will be significantly larger, due to indexing and other overheads)")



if __name__ == "__main__":
	import sys
	if len(sys.argv) != 4:
		print(f"USAGE: python3 {sys.argv[0]} encrypted_video.mp4 decrypted_video.mp4 database.db")
		exit()
	
	db_path, source_path, dest_path = sys.argv[1:]

	populate_db(db_path, source_path, dest_path)
