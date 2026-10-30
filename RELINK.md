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
You need a Mac with Xcode, Python 3.12 or newer (the `python3` that comes with macOS is too old: the builder unpacks with
`tarfile` filters), and these tools in one folder, as `bin/meson`, `bin/ninja` and `bin/pkg-config`: meson 1.4.2,
ninja 1.13.0 and pkgconf 2.5.1 (pinned in `apple/pins/ffmpeg-source.json`). For example:

```
python3.12 -m pip install --target ~/alkemyo-tools meson==1.4.2 ninja==1.13.0
```

then add `bin/meson` and `bin/ninja` wrappers that run them with that `PYTHONPATH`, and build pkgconf 2.5.1 into
`~/alkemyo-tools/bin/pkg-config`.

FFmpeg's `configure` refuses paths with spaces. Clone this repository, and keep `--work`, `--tools` and the download
cache, in folders whose paths have no spaces. The cache is `cache/` inside the clone unless you set
`ALKEMYO_PLAYER_CACHE` to another folder.

1. Get the sources. Download `ffmpeg-8.1.2.tar.xz` and `mpv-41f6a645.tar.gz` from this repository's `build-57` release
   (check them with `shasum -a 256 -c SHA256SUMS`), and put the FFmpeg archive at
   `<cache>/ffmpeg-expanded/downloads/ffmpeg-8.1.2.tar.xz`. Without it the builder downloads the same file from
   ffmpeg.org. The statically linked libraries come from MPVKit's prebuilt archives, which the builder downloads from
   GitHub and checks against `apple/pins/prebuilt-dependencies.json`. Their sources are also release assets.
2. Build both frameworks:

   ```
   python3.12 apple/build.py ios --work ~/alkemyo-work --tools ~/alkemyo-tools --archive <folder>/mpv-41f6a645.tar.gz
   ```

   Use `tvos` instead of `ios` for Apple TV. This writes `AlkemyoFFmpeg.xcframework` and `AlkemyoMPV.xcframework` to
   `output/ios` (or `output/tvos`), with their build receipts. Make your changes to the sources or patches first. A build
   you can use has to keep the same public C API.
3. Unpack an alkemyo build you have (`unzip <file>.ipa`). The app is `Payload/Alkemyo iPad.app` for iPhone and iPad and
   `Payload/alkemyo TV.app` for Apple TV.
4. Replace `Frameworks/AlkemyoFFmpeg.framework` and `Frameworks/AlkemyoMPV.framework` inside the app with the device
   slices of your build: `output/ios/AlkemyoFFmpeg.xcframework/ios-arm64/AlkemyoFFmpeg.framework` and
   `output/ios/AlkemyoMPV.xcframework/ios-arm64/AlkemyoMPV.framework` (for Apple TV, `output/tvos/.../tvos-arm64/...`).
   Delete each copied framework's `Headers` folder. Leave `AlkemyoAutomail.framework` as it is.
5. Re-sign with your own Apple development certificate and a provisioning profile for the app's bundle identifier and
   your device. Sign the two frameworks first, then the app with its entitlements, and put your profile in the app as
   `embedded.mobileprovision`:

   ```
   codesign -d --entitlements :- "Payload/Alkemyo iPad.app" > entitlements.plist
   codesign --force --sign "<your identity>" "Payload/Alkemyo iPad.app/Frameworks/AlkemyoFFmpeg.framework"
   codesign --force --sign "<your identity>" "Payload/Alkemyo iPad.app/Frameworks/AlkemyoMPV.framework"
   codesign --force --sign "<your identity>" --entitlements entitlements.plist "Payload/Alkemyo iPad.app"
   ```

   Edit `entitlements.plist` first so that the application identifier and team are yours. The Apple TV app also has a
   Top Shelf extension in `PlugIns/`: re-sign it the same way, with its own entitlements and profile, before the app.
6. Turn on Developer Mode on the device, then install the app with
   `xcrun devicectl device install app --device <device id> "Payload/Alkemyo iPad.app"`. alkemyo calls these frameworks
   only through their public C API, so a compatible build loads without changes to the app.

Apple's platform rules decide how you can install a re-signed app. This repository does not include, and will never include, alkemyo's signing keys.

## Help
If a step doesn't work for a released build, email alkemyomedia@gmail.com with the build number.
