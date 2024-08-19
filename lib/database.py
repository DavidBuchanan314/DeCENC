"""
Since we're working with large volumes of data, passed between multiple components, we need some way to store
our progress (especially, partial progress).

sqlite is used to persist this state

NOTE TO SELF: stop thinking about how to handle CBCS

make it work for CENC first, *then* think about CBCS


ugh no I'm thinking about CBCS again. Both problems can be reduced to finding AES block mappings from raw
plaintext to raw ciphertext.

CTR mode is "special" because the plaintexts are sequential numbers, which we could use as an optimisation but... let's just not

we'll assume, for now, that there's only one key_id in use at a time.
"""

import sqlite3
import os

def init_db(filename: str) -> sqlite3.Connection:
	# delete if exists
	try:
		os.remove(filename)
	except OSError:
		pass

	con = sqlite3.connect(filename)
	cur = con.cursor()

	cur.execute("PRAGMA journal_mode=WAL")

	cur.execute("""
		CREATE TABLE meta (
			input_path TEXT,
			output_path TEXT,
			cenc_mode TEXT,
			key_id BLOB NOT NULL
		);
	""")


	cur.execute("""
		CREATE TABLE pssh (
			pssh_box BLOB NOT NULL
		);
	""")

	cur.execute("""
		CREATE TABLE aes_blocks (
			aes_block_id INTEGER PRIMARY KEY NOT NULL,
			aes_in BLOB NOT NULL,
			aes_out BLOB
		)
	""")

	# we'll want to do quick lookups when we're doing the final file decrypt
	cur.execute("CREATE INDEX aes_ct ON aes_blocks (aes_in)")
	# ok maybe not, the index makes writes sloooooow, and most of our reads will be sequential-ish

	con.commit()

	return con


if __name__ == "__main__":
	init_db("test.db")
