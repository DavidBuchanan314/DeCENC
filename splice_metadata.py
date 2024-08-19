"""

We need to:

- Patch up stsd (indicate that file is encrypted, add scheme information, incl keyid)
- Add pssh boxes to moov
- Add saiz/saio/tenc to each moof

"""

import sqlite3
import os
import io
from lib.boxxy import Box, OpaqueBox, Moov, Moof, Traf, Trun, Saiz, Saio, Senc, Sinf, Schm, Schi, Tenc
from lib.util import tellable_bufferedreader, tellable_bufferedwriter
from yuvgen import DECENC_MAGIC, WIDTH, HEIGHT, AES_BLOCKS_PER_FRAME

def do_splice(db_filename, input_filename, output_filename, tracktype):
	is_audio = tracktype == "audio"
	con = sqlite3.connect(db_filename)
	cur = con.cursor()
	#cur.execute("pragma journal_mode=wal")

	key_id = cur.execute("SELECT key_id FROM meta").fetchone()[0]

	#input_filename = "test.mp4"
	#inlength = os.stat(input_filename).st_size
	#instream = open(input_filename, "rb")
	instream = tellable_bufferedreader(io.FileIO(input_filename, "rb"))


	#output_filename = "spliced.mp4"
	outstream = tellable_bufferedwriter(io.FileIO(output_filename, "wb"))

	BYTES_PER_MB = 0x182
	sample_template = {
		"iv": None,
		"subsamples": [{
			"clearbytes": 0x82,
			"encbytes": 0x100
		} for _ in range(AES_BLOCKS_PER_FRAME//16+1)] # TODO: don't hardcode that
	}
	sample_template["subsamples"][-1]["clearbytes"] = 0x204 # TODO: is this correct?
	sample_template["subsamples"][-1]["encbytes"] = 0

	parsectx = {}
	while True:
		if "box_offsets" in parsectx: # if we didn't do this, we'd leak memory like crazy, lol
			del parsectx["box_offsets"]

		try:
			box = Box.parse(instream, parsectx)
		except EOFError:
			break

		if isinstance(box, Moov):
			# XXX: we might have to handle the case where the audio track expects a different keyid
			if is_audio:
				mp4a = box.findall(b"mp4a")[0]
				mp4a.boxtype = b"enca" # a bit of a hack
				mp4a.children.append(Sinf([
					OpaqueBox(b"frma", b"mp4a"),
					Schm(scheme_type=b"cenc", scheme_version=(1, 0)),
					Schi([
						Tenc(
							default_isProtected=1,
							default_Per_Sample_IV_Size=16,
							default_KID=key_id
						)
					])
				]))
			else:
				stsd = box.findall(b"stsd")[0]
				avc1 = stsd.children[0]
				og_type = avc1.boxtype
				avc1.boxtype = b"encv" # a bit of a hack
				avc1.children.append(Sinf([
					OpaqueBox(b"frma", og_type),
					Schm(scheme_type=b"cenc", scheme_version=(1, 0)),
					Schi([
						Tenc(
							default_isProtected=1,
							default_Per_Sample_IV_Size=16,
							default_KID=key_id
						)
					])
				]))

			for psshblob, *_ in cur.execute("SELECT pssh_box FROM pssh"):
				pssh = Box.parse(io.BytesIO(psshblob), {})
				#print("Adding pssh:", pssh)
				box.children.append(pssh)

			box.write_into(outstream, {})
			continue

		if isinstance(box, Moof):
			# only log progress here so the ealier header logs don't get clobbered
			#print(f"\rSplice progress: {instream.tell()}/{inlength} input file bytes processed ({(100*instream.tell()/inlength):.2f}%)", end="")

			if is_audio:
				traf = box/Traf
				trun = box/Traf/Trun

				mdat: OpaqueBox = OpaqueBox.parse(instream, parsectx)
				assert(mdat.boxtype == b"mdat")

				#checksum = sum(x["clearbytes"] + x["encbytes"] for x in sample_template["subsamples"])
				#print("\n\n", hex(checksum), hex(len(mdat.body)), file=sys.stderr)
				#assert(checksum == len(mdat.body))

				sample_infos = []
				for run in trun.truns:
					sample_infos.append({
						"iv": b"A"*16,
						"subsamples": [{
							"clearbytes": run["sample_size"],
							"encbytes": 0
						}]
					})

				saiz = Saiz(
					default_sample_info_size=16+2+6,
					sample_count=len(sample_infos),
				)
				saio = Saio(offset=[0xdead]) # to be replaced later
				senc = Senc(
					flags=Senc.Flags.use_subsample_encryption,
					sample_info=sample_infos
				)

				orig_len = len(bytes(box))
				traf.children += [saiz, saio, senc]
				len_delta = len(bytes(box)) - orig_len

				offsets = box.bake_offsets()
				trun.data_offset += len_delta
				saio.offset[0] = offsets[senc] + 0x10

				box.write_into(outstream, {})
				mdat.write_into(outstream, {})
				continue
			else:
				traf = box/Traf
				trun = box/Traf/Trun

				mdat: OpaqueBox = OpaqueBox.parse(instream, parsectx)
				assert(mdat.boxtype == b"mdat")

				# parse the metadata we embedded into the frame pixels
				start_offset = mdat.body.index(DECENC_MAGIC)
				iv_lo = mdat.body[start_offset+32+16*2:start_offset+32+16*3]
				iv_hi = mdat.body[start_offset+32+16*3:start_offset+32+16*4]
				iv = bytes.fromhex((iv_hi+iv_lo).decode())
				
				sample_template["iv"] = iv
				sample_template["subsamples"][0]["clearbytes"] = start_offset + BYTES_PER_MB # skip to first non-metadata block

				initial_total = sum(x["clearbytes"] + x["encbytes"] for x in sample_template["subsamples"][:-1])
				sample_template["subsamples"][-1]["clearbytes"] = len(mdat.body) - initial_total

				#checksum = sum(x["clearbytes"] + x["encbytes"] for x in sample_template["subsamples"])
				#print("\n\n", hex(checksum), hex(len(mdat.body)), file=sys.stderr)
				#assert(checksum == len(mdat.body))

				saiz = Saiz(
					default_sample_info_size=0,
					sample_count=1,
					sample_info_size=[16+2+6*len(sample_template["subsamples"])]
				)
				saio = Saio(offset=[0xdead]) # to be replaced later
				senc = Senc(
					flags=Senc.Flags.use_subsample_encryption,
					sample_info=[sample_template]
				)

				orig_len = len(bytes(box))
				traf.children += [saiz, saio, senc]
				len_delta = len(bytes(box)) - orig_len

				offsets = box.bake_offsets()
				trun.data_offset += len_delta
				saio.offset[0] = offsets[senc] + 0x10

				box.write_into(outstream, {})
				mdat.write_into(outstream, {})
				continue

		box.write_into(outstream, {}) # other box type, just copy it

	#print()

if __name__ == "__main__":
	import sys
	if len(sys.argv) != 5:
		print(f"USAGE: python3 {sys.argv[0]} db_path.db input.mp4 output.mp4 audio|video")
		exit()
	
	do_splice(*sys.argv[1:])
