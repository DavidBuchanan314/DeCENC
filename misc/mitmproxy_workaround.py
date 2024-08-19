"""
mitmdump -s misc/mitmproxy_workaround.py -p 4444 --mode reverse:http://localhost:8080/

workaround for https://github.com/mitmproxy/mitmproxy/issues/6620
"""

from mitmproxy import http

def websocket_message(flow: http.HTTPFlow):
	assert flow.websocket is not None  # make type checker happy
	flow.websocket.messages = flow.websocket.messages[-1:] # throw away all but the most recent message
