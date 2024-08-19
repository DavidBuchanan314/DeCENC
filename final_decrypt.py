import sqlite3
import os
import io
import shutil
from lib.boxxy import Box, OpaqueBox, Moov, Pssh, Moof, Traf, Senc
from lib.util import xor_bytes

con = sqlite3.connect("test.db")
cur = con.cursor()
#cur.execute("pragma journal_mode=wal")

blocks_remaining = cur.execute("SELECT COUNT(*) FROM aes_blocks WHERE aes_out IS NULL").fetchone()[0]
assert(blocks_remaining == 0)

source_path, dest_path = cur.execute("SELECT input_path, output_path FROM meta").fetchone()
print(f"Writing to {dest_path!r}")

shutil.copyfile(source_path, dest_path)

file_length = os.stat(source_path).st_size
filestream = open(source_path, "rb")

destfile = open(dest_path, "rb+")

parsectx = {}
while filestream.tell() < file_length:
	print(f"\rFinal decrypt progress: {filestream.tell()}/{file_length} file bytes processed ({(100*filestream.tell()/file_length):.2f}%)", end="")
	box = Box.parse(filestream, parsectx)
	
	if isinstance(box, Moof):
		mdat_offset = filestream.tell()
		mdat: OpaqueBox = OpaqueBox.parse(filestream, parsectx)
		assert(mdat.boxtype == b"mdat")

		try:
			senc = box/Traf/Senc
		except ZeroDivisionError:
			continue # not encrypted
		msg_idx = 0
		destfile.seek(mdat_offset + 8)
		for sample in senc.sample_info:
			iv_int = int.from_bytes(sample["iv"].ljust(16, b"\0"), "big")
			ciphertext = b""
			if senc.flags & Senc.Flags.use_subsample_encryption:
				for ss in sample["subsamples"]:
					msg_idx += ss["clearbytes"]
					ciphertext += mdat.body[msg_idx:msg_idx+ss["encbytes"]]
					msg_idx += ss["encbytes"]
			else:
				raise Exception("TODO")
			num_blocks = (len(ciphertext) + 15) // 16 # round up
			cipher_blocks = [(iv_int + i).to_bytes(16, "big") for i in range(num_blocks)]
			keystream = b"".join(cur.execute("SELECT aes_out FROM aes_blocks WHERE aes_in=?", (block,)).fetchone()[0] for block in cipher_blocks)[:len(ciphertext)]
			plaintext = io.BytesIO(xor_bytes(ciphertext, keystream))

			if senc.flags & Senc.Flags.use_subsample_encryption:
				for ss in sample["subsamples"]:
					destfile.seek(destfile.tell() + ss["clearbytes"])
					destfile.write(plaintext.read(ss["encbytes"]))
			else:
				raise Exception("TODO")


print()
print("Done!")
