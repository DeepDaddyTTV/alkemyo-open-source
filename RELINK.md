# Rebuilding and relinking

The LGPL lets you change these libraries and run alkemyo with your changed copy. Here is how to do that on each platform.

## Linux
1. Build the runtime with `linux/build-player-in-docker.sh`, which wraps `build-linux-player.py` on Ubuntu 22.04. It checks every tarball's sha256, checks that FFmpeg reports "LGPL version 2.1 or later" and that mpv's `gpl` option is off, and sets RUNPATH to `$ORIGIN`.
2. Either replace `libmpv.so.2` (and the FFmpeg `.so` files) in `/opt/alkemyo/lib`, or start alkemyo with `--private-runtime /path/to/libmpv.so.2`.
3. alkemyo needs the libmpv 2 client API (`mpv_client_api_version` major 2). A newer compatible build works.

## Windows
1. Build libmpv-2.dll with the LGPL configuration in `windows/dependencies.json` and `compile-lgpl-libmpv.patch`.
2. Replace `libmpv-2.dll` in the alkemyo folder. alkemyo records that the runtime is not the shipped one, but it doesn't refuse it. It needs only the libmpv 2 client API.

## iPhone, iPad and Apple TV
1. On a Mac with Xcode, run `python3 apple/build.py ios --work <folder> --tools <folder>` (or `tvos`). `--tools` holds `bin/meson`, `bin/ninja` and `bin/pkg-config`, and the paths must not contain spaces. It builds `AlkemyoFFmpeg.framework` and `AlkemyoMPV.framework` from the pinned sources and patches into `output/ios` or `output/tvos`, with their build receipts.
2. Replace the two frameworks inside `alkemyo.app/Frameworks/` of an alkemyo build you have.
3. Re-sign the app with your own Apple development certificate and provisioning profile (for example with `codesign`, or an Xcode re-signing tool), then install it on your own device. alkemyo calls these frameworks only through their public C API, so a compatible build loads without changes to the app.

Apple's platform rules decide how you can install a re-signed app. This repository does not include, and will never include, alkemyo's signing keys.

## Help
If a step doesn't work for a released build, email alkemyomedia@gmail.com with the build number.
