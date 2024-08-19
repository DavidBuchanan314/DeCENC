#!/usr/bin/env python3

from typing import Tuple, Optional
import aiohttp
from aiohttp import web
from lib.util import humanize, percent_fmt
import aiohttp_cors
import subprocess
import html
import sqlite3
import os
import shutil
import time
import datetime
import asyncio
from lib.process_recording import process_y4m

start_time = time.time()

Y4M_PORT = 3000
HTTP_PORT = 8080
DB_PATH = "test.db"

MP4_BLOCK_SIZE = 0x10000
mp4_bytes_sent = 0

con = sqlite3.connect(DB_PATH)

routes = web.RouteTableDef()

def render_table(title: str, rows: Tuple[str, str, Optional[str]]) -> str:
	rendered_rows = []
	for name, value, tooltip in rows:
		rendered_rows.append(f"\t\t\t\t\t<tr{' name="' + html.escape(tooltip) + '"' if tooltip else ''}><td>{html.escape(name)}</td><td>-></td><td>{html.escape(value)}</td></tr>")
	return f"""
		<section>
			<h3>{html.escape(title)}</h3>
			<div>
				<table>\n{'\n'.join(rendered_rows)}
				</table>
			</div>
		</section>"""

prev_stats = None

@routes.get("/")
async def dashboard(request):
	global prev_stats

	cur = con.cursor()

	in_path, out_path, cenc_mode, key_id = cur.execute("SELECT input_path, output_path, cenc_mode, key_id FROM meta").fetchone()
	db_size = os.stat(DB_PATH).st_size
	file_size = os.stat(in_path).st_size
	disk_free = shutil.disk_usage(DB_PATH).free
	total_blocks = cur.execute("SELECT COUNT(*) FROM aes_blocks").fetchone()[0]
	blocks_found = cur.execute("SELECT COUNT(*) FROM aes_blocks WHERE aes_out IS NOT NULL").fetchone()[0]

	template = open("./webui/index.html").read()
	body = ""
	body += render_table("Configuration", [
		("Input file", in_path, None),
		("Output file", out_path, None),
		("File size", f"{file_size} ({humanize(file_size)})", None),
		("CENC mode", cenc_mode, None),
		("Key ID", key_id.hex(), None)
	])
	body += render_table("Progress", [
		("DB size on disk", f"{db_size} ({humanize(db_size)})", None),
		("Free disk space", f"{disk_free} ({humanize(disk_free)})", None),
		("Recovered AES blocks", f"{blocks_found}/{total_blocks} ({percent_fmt(blocks_found, total_blocks)})" + (" DONE!" if total_blocks == blocks_found else ""), None)
	])

	time_now = time.time()
	if prev_stats:
		prev_time, prev_blocks, prev_mp4_bytes = prev_stats
		uptime = int(time_now-start_time)
		dt = time_now - prev_time
		new_blocks = blocks_found - prev_blocks
		new_mp4_sent = mp4_bytes_sent - prev_mp4_bytes
		body += render_table("Stats", [
			("Server uptime", str(datetime.timedelta(seconds=uptime)), None),
			("Stat interval", f"{dt:.1f}s", None),
			("New blocks found", f"{new_blocks} ({humanize(int(new_blocks*16/dt))}/s)", None),
			("Generated MP4", f"{new_mp4_sent} bytes ({humanize(int(new_mp4_sent/dt))}/s)", None),
		])
	prev_stats = (time_now, blocks_found, mp4_bytes_sent)

	rendered = template.replace("<!--BODY-->", body)
	return web.Response(body=rendered, content_type="text/html")

@routes.get("/crafted_video.mp4")
async def crafted_video(request):
	global mp4_bytes_sent

	ws = web.WebSocketResponse()
	await ws.prepare(request)

	print("starting mp4gen")
	devnull = open("/dev/null", "wb")
	# XXX: this can create zombie processes if we don't exit cleanly
	process = subprocess.Popen("./mp4gen.sh", stdout=subprocess.PIPE, stderr=devnull)

	try:
		async for msg in ws:
			if msg.type == aiohttp.WSMsgType.TEXT:
				if msg.data == "gimme":
					#print("gimme vid")
					buf = process.stdout.read(MP4_BLOCK_SIZE)
					mp4_bytes_sent += len(buf)
					if not buf:
						await ws.close()
						break
					await ws.send_bytes(buf)
			elif msg.type == aiohttp.WSMsgType.ERROR:
				print(f'ws connection closed with exception {ws.exception()}')

		print("closing ws")
		return ws
	finally:
		print("killing mp4gen")
		process.kill()


# TODO: get rid of the repetition here!
@routes.get("/silence.mp4")
async def silent_audio(request):
	global mp4_bytes_sent

	ws = web.WebSocketResponse()
	await ws.prepare(request)

	print("starting generate_silence")

	devnull = open("/dev/null", "wb")
	# XXX: this can create zombie processes if we don't exit cleanly
	process = subprocess.Popen("./generate_silence.sh", stdout=subprocess.PIPE, stderr=devnull)

	try:
		async for msg in ws:
			if msg.type == aiohttp.WSMsgType.TEXT:
				if msg.data == "gimme":
					#print("gimme aud")
					buf = process.stdout.read(MP4_BLOCK_SIZE)
					mp4_bytes_sent += len(buf)
					if not buf:
						await ws.close()
						break
					await ws.send_bytes(buf)
			elif msg.type == aiohttp.WSMsgType.ERROR:
				print(f'ws connection closed with exception {ws.exception()}')

		print("closing audio ws")
		return ws
	finally:
		print("killing generate_silence")
		process.kill()





async def y4m_handle_client(reader, writer):
	print("Handling Y4M stream input")
	try:
		# TODO: think about how to report stats live
		success = await process_y4m(con, reader, hevc_mode=False)
		print("Y4M stream ended. success:", success)
		# TODO: consider shutting down the server on success?
	finally:
		writer.close()


async def y4m_server():
	server = await asyncio.start_server(y4m_handle_client, "0.0.0.0", Y4M_PORT)
	print("started y4m server")
	async with server:
		await server.serve_forever()







app = web.Application()
app.add_routes(routes)
cors = aiohttp_cors.setup(app, defaults={
		"*": aiohttp_cors.ResourceOptions(
			allow_credentials=True,
			expose_headers="*",
			allow_headers="*"
		)
	})
for route in app.router.routes():
	cors.add(route)

async def main():
	runner = web.AppRunner(app)
	await runner.setup()
	site = web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
	await site.start()
	print("started http server")

	await y4m_server() # currently does not ever terminate

	await runner.cleanup()

if __name__ == "__main__":
	asyncio.run(main())
