```
.--.                                              .--.
|  |---------.      .-----------------------------|  |
|  |    _____ '.__.' _____ ______ _   _  _____    |  |
|  |   |  __ \  ___ / ____|  ____| \ | |/ ____|   |  |
|  |   | |  | |/ _ \ |    | |__  |  \| | |        |  |
|  |   | |  | |  __/ |    |  __| | . ` | |        |  |
|  |   | |__| |\___| |____| |____| |\  | |____    |  |
|  |   |_____/ .--. \_____|______|_| \_|\_____|   |  |
|  |_________.'    '._____________________________|  |
'--'                                              '--'
```

Please see [Phrack #71 0x06](http://phrack.org/issues/71/6.html#article) for a technical introduction to DeCENC.

[MPEG-CENC](https://docs.unified-streaming.com/documentation/drm/common-encryption.html) is an encrypted media container format commonly used by DRM systems, but it is not a DRM system in and of itself. Per [ISO/IEC 23001-7:2023](https://www.iso.org/standard/84637.html):

> "This document does not define a DRM system."

One of the demonstrations in this repo attacks a video playing through the [Encrypted Media Extensions](https://www.w3.org/TR/encrypted-media/) API. Similarly, EME is not itself a DRM system:

> "This specification does not define a content protection or Digital Rights Management system."

DeCENC breaks the MPEG-CENC encryption scheme, via the [EME+MSE interfaces](https://web.dev/articles/eme-basics).

> [!WARNING]
> DeCENC is security research tool. It may be used to test the effectiveness of systems that rely on MPEG-CENC to encapsulate protected content. Do not test against content that you are not authorized to decrypt, or that is "protected" using a protection mechanism that you are not authorized to circumvent, because doing so may violate the DMCA or related legislation, which would be unfortunate.

I'll aim to fix reported bugs, and/or merge PRs that I like, but if you reference (directly or euphemistically) illegal activity, specific DRM systems (except "clearkey"), or specific streaming platforms, I will close the issue without comment. You are welcome to fork the repo, under the terms of the MIT license.

## Initial Setup

We need a patched version of `x264`. Build the patched version like so:

```
git clone --recursive git@github.com:DavidBuchanan314/DeCENC.git

cd x264
git apply ../x264_force_pcm.patch
./configure
make
cd ../

# TODO: instructions for kvazaar
```

# Demos

## "Closed Loop" Demo

Simply execute `./testall.sh`. This runs the attack elements individually and headlessly, using ffmpeg as a pseudo-CDM with hardcoded content key.

If everything worked, you should now have a decypted copy of Big Buck Bunny at `./test_files/decrypted_inplace.mp4`, playable in a standard media player like `mpv`.

## "Open Loop" Demo

This demo simulates a "real world" attack against a DRM-enabled video streaming website. In this case the demo player uses the EME Clearkey key system (which isn't "real" DRM), but as mentioned in the write-up, the attack itself is generic, applicable to any CENC-enabled playback systems that conform to the relevant specs.

Initialise the AES block database with the test input file, and start the attack server.

```sh
python3 populate_db.py test.db ./test_files/bbb_144p_h264_enc.mp4 ./test_files/decrypted_inplace.mp4
python3 server.py
```

Visit the status dashboard in a browser: http://localhost:8080/

In another terminal session, start the demo EME player web server:

```
./serve_eme_demo.sh
```

Navigate to http://localhost:8069/eme_demo_player/ in Chromium (the attack itself does work in Firefox, but it doesn't like my demo player and I can't be bothered to work out why). You should be able to press play and watch the video as-is, but if you tried to save a copy of the video, you wouldn't be able to play it without knowing the key (in this case you can see the key in the demo player's source code, because the Clearkey system isn't real DRM - but pretend you can't see it!).

![image](https://github.com/DavidBuchanan314/DeCENC-dev/assets/13520633/f80d0595-ace5-4f07-a1de-c153a4090122)

For demonstration purposes, the MSE shim userscript is pre-loaded - there should be an "AutoPwn" button in the top-right corner of the webpage. Click it, and the attack will start. You should see the video element start playing what looks like random noise.

Next, you'll need to set up screen capture in some way. This could be an HDMI capture card, of for ease of testing, software screen recording like OBS. The attack server expects a yuv4mpeg video stream on port 3000. It is critical that the capture is 100% lossless, without scaling or colour-range remapping at any point in the pipeline. You may have to fiddle around a bit (a lot) with your capture setup to make things work. For troubleshooting, check the attack server's logs. For performance reasons, you won't want to capture the whole screen, just the portion with the video playing in it - some margin is OK though (the decoder script will locate the video frame automatically)

OBS tips: Make sure the width and height are multiples of 2. Output > Recording > Type=Custom Output (FFmpeg), Output Type=URL, URL=tcp://localhost:3000, container format=yuv4mpegpipe

Once you do have everything recording properly, it should look something like this:

![image](https://github.com/DavidBuchanan314/DeCENC-dev/assets/13520633/b175826f-c4e6-4799-b9e2-f24dbcf0db7d)

Once the progress on the dashboard reaches 100% (because the demo files are small, this should be near-instant), you can stop the server(s) and perform the final decryption step:

```
python3 final_decrypt.py
```

You should now have a decrypted and viewable video file at `./test_files/decrypted_inplace.mp4`! By the way, you might want to do a final remux pass with ffmpeg, to clean up the stray CENC metadata that's no longer necessary.

# Codebase Structure

TODO: explain which parts of the codebase do what
