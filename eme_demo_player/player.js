"use strict";

const SOURCE_URL = '../test_files/bbb_144p_h264_enc.mp4';
const SOURCE_MIME = 'video/mp4; codecs="avc1.64001F"';

const KEYS = {
	"AAAAAAAAAAAAAAAAAAAAAA": "AAAAAAAAAAAAAAAAAAAAAA" // urlsafe b64 nopad
}

// https://web.dev/articles/media-mse-basics
async function sourceOpen(e) {
	console.log("sourceOpen", e);
	//URL.revokeObjectURL(videoElem.src); // what is this for???
	let mediaSource = e.target;
	let sourceBuffer = mediaSource.addSourceBuffer(SOURCE_MIME);
	let videoUrl = SOURCE_URL;
	let res = await fetch(videoUrl);
	let resbuf = await res.arrayBuffer();
	sourceBuffer.addEventListener('updateend', function (e) {
		if (!sourceBuffer.updating && mediaSource.readyState === 'open') {
		//	mediaSource.endOfStream();
		}
	});
	sourceBuffer.appendBuffer(resbuf);
}

// https://github.com/ybandou/MSE-EME-ClearKey/blob/master/encrypted-media-clearKey-handler.js
function stringToArray(s)
{
	let array = new Uint8Array(s.length);
	for (let i = 0; i < s.length; i++) {
		array[i] = s.charCodeAt(i);
	}
	return array;
}

var keyInitDone = false;
async function onEncrypted(e) {
	console.log("onEncrypted", e);

	if (keyInitDone) return;

	let clearkey = await navigator.requestMediaKeySystemAccess("org.w3.clearkey", [{
		initDataTypes: [e.initDataType],
		videoCapabilities: [{contentType: SOURCE_MIME}]
	}]);

	let mediakeys = await clearkey.createMediaKeys();
	await e.target.setMediaKeys(mediakeys);

	let session = e.target.mediaKeys.createSession();

	console.log("created MediaKeySession");

	session.addEventListener("message", function (e) {
		console.log("message", e);
		let msg = JSON.parse(String.fromCharCode.apply(String, new Uint8Array(e.message)));
		console.log(msg);

		let outKeys = [];
		for (var i = 0; i < msg.kids.length; i++) {
			let kid = msg.kids[i];
			var key = KEYS[kid];
			if (key) {
				outKeys.push({
					"kty":"oct",
					"alg":"A128KW",
					"kid": kid,
					"k": key
				});
			}
		}
		var update = JSON.stringify({
			"keys" : outKeys,
			"type" : msg.type
		});

		console.log(update);

		session.update(stringToArray(update).buffer);
	});
	session.addEventListener("keystatuseschange", function (e) {
		console.log("keystatuseschange", e);
		let keysStatus = [...session.keyStatuses.entries()];
		console.log(keysStatus);
		// assume success
		keyInitDone = true;
	});

	session.generateRequest(e.initDataType, e.initData);
}

let videoElem = document.getElementById("player");
let mediaSource = new MediaSource();
mediaSource.addEventListener("sourceopen", sourceOpen);
videoElem.addEventListener("encrypted", onEncrypted);
videoElem.src = URL.createObjectURL(mediaSource);
