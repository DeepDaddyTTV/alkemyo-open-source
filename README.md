# alkemyo open-source components

This repository contains the open-source media libraries that alkemyo ships: the **LGPL** ones, plus the others they link to. For each alkemyo build it provides the exact source, our changes, the build scripts and the steps to rebuild and relink. It is how alkemyo meets the source and relinking terms of the GNU Lesser General Public License.

alkemyo itself, including its AUTOMAIL playback engine, is proprietary. It is **not** in this repository, and nothing here licenses it.

## What each platform ships

| Platform | Component | Version | Licence | How it's linked |
|---|---|---|---|---|
| iPhone, iPad, Apple TV | FFmpeg (AlkemyoFFmpeg.framework) | 8.1.2 | LGPL 2.1 or later (`--disable-gpl --disable-nonfree`) | dynamic framework |
| iPhone, iPad, Apple TV | mpv (AlkemyoMPV.framework) | 0.41.0, commit 41f6a645 | LGPL 2.1 or later (`-Dgpl=false`) | dynamic framework; libass, FriBidi, HarfBuzz, FreeType, libunibreak, libplacebo, Little CMS, libdovi, uchardet and libbluray are linked statically inside it |
| Linux | FFmpeg, mpv, libplacebo, dav1d, libdisplay-info | 8.1.2, 0.41.0, 7.360.1, 1.5.3, 0.2.0 | LGPL 2.1+ (dav1d BSD-2-Clause, libdisplay-info MIT) | shared libraries next to the app (`$ORIGIN`) |
| Windows | libmpv-2.dll (mpv with FFmpeg) | mpv-dev-lgpl 20261003 git-413ff0b1cd | LGPL 2.1 or later | DLL next to the app |
| Mac | not distributed yet | | | |
| Android | no LGPL native media libraries (it uses AndroidX Media3, Apache 2.0) | | | |

## Layout

- `LICENSES/`: the full texts of LGPL-2.1, LGPL-3.0 and GPL-3.0. LGPLv3 is a set of extra permissions on top of GPLv3, so both texts are kept.
- `apple/`: the iOS and tvOS framework builder (`build.py`, which uses `apple_player.py`), its pins and allow-list, and our mpv changes in `patches/`:
  - `libmpv_alkemyo.c`, an LGPL file built into mpv, and the `alkemyo_native_buffer.h` header it includes;
  - the tvOS AVFoundation audio patch.
  `pins/prebuilt-dependencies.json` lists the archives (and their sha256) that the mpv framework statically links.
- `linux/`: `build-linux-player.py`, `linux-player-sources.json` (pinned tarballs, with sha256 and the mpv git tree id), and the Ubuntu 22.04 Docker entry point.
- `windows/`: the runtime's `dependencies.json`, the LGPL compile patch and SHA256SUMS.
- `RELINK.md`: how to build your own copy of each library and use it with alkemyo.

## Exact sources

Each alkemyo build that ships these libraries gets a **GitHub Release** in this repository, tagged with the build (for example `build-57`). Its assets are the exact upstream source archives used, listed with their sha256 in the build's folder (for Build 57, `build-57/`: `README.md`, `manifest.json` and `SHA256SUMS`). The builders refuse any archive whose checksum doesn't match.

Upstream sources:
- FFmpeg: https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz
- mpv: https://github.com/mpv-player/mpv/tree/v0.41.0
- libplacebo: https://code.videolan.org/videolan/libplacebo
- FriBidi: https://github.com/fribidi/fribidi
- libbluray: https://code.videolan.org/videolan/libbluray
- The rest are listed in `apple/pins/apple-player-allowlist.json`.

## Contact

alkemyomedia@gmail.com, for source requests or questions about these components.
