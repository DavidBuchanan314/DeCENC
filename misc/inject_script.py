"""
mitmdump -s misc/inject_script.py --no-http2 --listen-port 8084 --allow-hosts example.com
chromium-browser --proxy-server="localhost:8084"
mitmdump -p 4444 --mode reverse:http://localhost:8080/
"""

from mitmproxy import http

def response(flow: http.HTTPFlow):
	if flow.request.host == "example.com" and flow.request.path.startswith("/video_player/"):
		flow.response.content = flow.response.content.replace(b"<head>", b"<head><script>" + open("./misc/mse_hijack.js", "rb").read() + b"</script>")
