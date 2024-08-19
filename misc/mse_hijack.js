// ==UserScript==
// @name         New Userscript
// @namespace    http://tampermonkey.net/
// @version      2024-01-20
// @description  blah
// @author       You
// @match        https://example.com/video_player
// @icon         https://www.google.com/s2/favicons?sz=64&domain=example.com
// @grant        none
// ==/UserScript==

/*

This script is not anywhere near as "refined" as I'd like it to be. In theory it could be more automatic,
but in practice you'll need to fiddle with it a lot.

*/

(function() {
    'use strict';

    const HAX_SERVER = "ws://localhost:8080";
    //const HAX_SERVER = "wss://192.168.0.80:4444";

    document.addEventListener('DOMContentLoaded', function() {

        let gui = document.createElement("div");
        gui.style.all = "initial";
        gui.style.position = "fixed";
        gui.style.top = 0;
        gui.style.right = 0;
        gui.style.zIndex = 999999999999;
        gui.style.backgroundColor = "#fff";
        gui.style.padding = "1em";
        gui.style.border = "1px solid black";
        gui.style.fontFamily = "sans-serif";
    
        gui.innerText = "DeCENC MSE Helper";
    
        let go = document.createElement("input");
        go.type = "button";
        go.value = "AutoPwn!";
        go.style.all = "revert";
        go.style.display = "block";
        go.onclick = () => {window.autoPwn()};
    
        gui.appendChild(go);
    
        document.body.appendChild(gui);
    }, false);


// RESOLUTION FAKING

    let getWidth = function() {
        console.log("hooked getWidth");
        return 3840;
    };
    Object.defineProperty(window.Screen.prototype, 'width', {
        get: getWidth,
        set: Object.getOwnPropertyDescriptor(window.Screen.prototype, 'width').set,
        enumerable: true,
        configurable: true
    });

    let getHeight = function() {
        console.log("hooked getHeight");
        return 2160;
    };
    Object.defineProperty(window.Screen.prototype, 'height', {
        get: getHeight,
        set: Object.getOwnPropertyDescriptor(window.Screen.prototype, 'height').set,
        enumerable: true,
        configurable: true
    });

    let getAvailWidth = function() {
        console.log("hooked getAvailWidth");
        return 3840;
    };
    Object.defineProperty(window.Screen.prototype, 'availWidth', {
        get: getAvailWidth,
        set: Object.getOwnPropertyDescriptor(window.Screen.prototype, 'availWidth').set,
        enumerable: true,
        configurable: true
    });

    let getAvailHeight = function() {
        console.log("hooked getAvailHeight");
        return 2160;
    };
    Object.defineProperty(window.Screen.prototype, 'availHeight', {
        get: getAvailHeight,
        set: Object.getOwnPropertyDescriptor(window.Screen.prototype, 'availHeight').set,
        enumerable: true,
        configurable: true
    });




    window.sourceBuffers = [];

    let asb = window.MediaSource.prototype.addSourceBuffer;
    window.MediaSource.prototype.addSourceBuffer = function(mimeType) {
        /*if (mimeType.startsWith("video")) {
            mimeType = 'video/mp4;codecs="avc1.64000b"';
        }*/
        console.log("addSourceBuffer:", mimeType);
        let sb = asb.call(this, mimeType);
        sb.mimetype = mimeType;
        sb.parent = this;
        window.sourceBuffers.push(sb);
        return sb;
    }

    const BUFFER_TARGET = 5; // seconds

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function ws_connect(url) {
        return new Promise(function(resolve, reject) {
            var ws = new WebSocket(url);
            ws.binaryType = "arraybuffer";
            ws.onopen = function() {
                resolve(ws);
            };
            ws.onerror = function(err) {
                reject(err);
            };

        });
    }

    function ws_send_and_wait(ws, msg) {
        return new Promise(function(resolve, reject) {
            ws.onmessage = function (evt) {
                delete ws.onmessage;
                //console.log(evt);
                resolve(evt.data);
            };
            ws.send(msg);
        });
    }

    // this is so janky lol
    async function feedsource(sourcebuf, sourceurl) {
        const ws = await ws_connect(sourceurl);

        async function pump() {
            const buf = await ws_send_and_wait(ws, "gimme");
            while (sourcebuf.updating) {
                await sleep(10); // so cursed...
            }
            sbab.call(sourcebuf, buf);
            return true;
        }

        while (await pump()) {

            // loop until another pump is needed
            while (true) {
                await sleep(10);
                let buffered_timestamp = 0;
                let buf_min = 999999999;
                const bufinfo = buffered_getter.call(sourcebuf);
                for (let i=0; i<bufinfo.length; i++) {
                    if (bufinfo.end(i) > buffered_timestamp) {
                        buffered_timestamp = bufinfo.end(i);
                    }
                    if (bufinfo.start(i) < buf_min) {
                        buf_min = bufinfo.start(i);
                    }
                }
                const currentTime = sourcebuf.parentVideo ? ct.call(sourcebuf.parentVideo) : 0.0;
                //console.log(currentTime, buffered_timestamp);
                if (currentTime + BUFFER_TARGET > buffered_timestamp) {
                    // this is an ugly hack, this logic should probably
                    // be somewhere else. the point is to un-buffer already-played video
                    // so the buffer doesn't get full.
                    if (!sourcebuf.updating && (currentTime - buf_min) > 10) {
                        sourcebuf.remove(buf_min, currentTime - 5);
                    }

                    break; // break out of the wait loop, to trigger another pump
                }

                // at this point there should be enough buffer to play?
                if (sourcebuf.parentVideo && sourcebuf.parentVideo.paused) { // seems like it auto-pauses on buffer underrun
                    await sourcebuf.parentVideo.play();
                }
            }
        }
    }

    window.SourceBuffer.prototype.hijack = function(hijacked_src) {
        this.hijacked = true;
        console.log("dropping buffers");
        if (this.parentVideo) {
            this.parentVideo.pause();
        }
        this.abort();
        const bufinfo = buffered_getter.call(this);
        for (let i=0; i<bufinfo.length; i++) {
            this.remove(bufinfo.start(i), bufinfo.end(i));
        }
        //sct.call(this.parentVideo, 0);
        console.log("triggering custom loader");
        feedsource(this, hijacked_src);
    }

    let sbab = window.SourceBuffer.prototype.appendBuffer;
    window.SourceBuffer.prototype.appendBuffer = function(source) {
        if (this.hijacked) {
            console.log("page tried to appendBuffer on hijacked SourceBuffer. Dropping", source.byteLength);
            return;
        }
        return sbab.call(this, source);
    }

    let buffered_getter = Object.getOwnPropertyDescriptor(window.SourceBuffer.prototype, 'buffered').get ;
    let buffered = function() {
        //let res = buffered_getter.call(this);
        //console.log("get buffered", JSON.stringify([...Array(res.length).keys()].map((i) => [res.start(i), res.end(i)])));
        //return res;
        return { // pretend to be maximally buffered
            length: 1,
            start: ()=>0,
            end: ()=>999999999,
        }
    };
    Object.defineProperty(window.SourceBuffer.prototype, 'buffered', {
        get: buffered,
        set: undefined,
        enumerable: true,
        configurable: true
    });


    let ct = Object.getOwnPropertyDescriptor(window.HTMLMediaElement.prototype, 'currentTime').get;
    let sct = Object.getOwnPropertyDescriptor(window.HTMLMediaElement.prototype, 'currentTime').set;
    let currentTime = function() {
        if (this.frozenTime) {
            return this.frozenTime; // you'd do video.frozenTime = video.currentTime, during hijack
        }
        let res = ct.call(this);
        //console.log("currentTime", res);
        return res;
    };
    let setCurrentTime = function(value) {
        if (this.frozenTime) {
            console.log("Someone tried to set currentTime, but we're frozen", value);
            /*try {
                // Code throwing an exception
                throw new Error();
            } catch(e) {
                console.log(e.stack);
            }*/
            return;
        }
        sct.call(this, value);
    }
    Object.defineProperty(window.HTMLMediaElement.prototype, 'currentTime', {
        get: currentTime,
        set: setCurrentTime,
        enumerable: true,
        configurable: true
    });

    // put window at native scale in the top-left corner of the page
    window.fixVideo = function (video) {
        video.style.zIndex = 99999999999;
        video.style.position = "fixed";
        video.style.top = 0;
        video.style.left = 0;
        video.style.margin = 0;
        video.style.padding = 0;
        video.style.transform = "unset";
        video.style.cssText += "width: initial !important; height: initial !important;";
    }

    window.autoPwn = function () {
        //let playing_videos = Array.from(document.querySelectorAll("video")).filter(v=>!v.paused);
        let playing_videos = Array.from(document.querySelectorAll("video"));
        if (playing_videos.length !== 1) {
            console.log("Could not uniquely identify a playing video.")
            return;
        }
        let video = playing_videos[0];
        window.fixVideo(video); // fix up video css
        video.frozenTime = video.currentTime; // freeze reported playback timestamp*/
        //let video = null;
        let videoSourceBuffer = window.sourceBuffers[0]; // XXX: this is a guess, should be more inteligent
        videoSourceBuffer.parentVideo = video;
        videoSourceBuffer.hijack(HAX_SERVER + "/crafted_video.mp4");
        //let audioSourceBuffer = window.sourceBuffers[0]; // XXX: likewise
        //audioSourceBuffer.parentVideo = video;
        //audioSourceBuffer.hijack(HAX_SERVER + "/silence.mp4");
    }

    console.log("loaded");
    /*window.SourceBuffer.prototype.abort = function(){
        console.log("abort");
    }
    window.SourceBuffer.prototype.changeType = function(type){
        console.log("changeType", type);
    }*/
})();
