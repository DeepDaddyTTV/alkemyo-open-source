# Build 57 sources

These are the exact upstream sources behind the player libraries in alkemyo Build 57 for iPhone, iPad and Apple TV:
`AlkemyoFFmpeg.framework` (FFmpeg) and `AlkemyoMPV.framework` (mpv, with the libraries below linked statically inside it).
Each archive is an asset of the `build-57` GitHub Release in this repository. `manifest.json` has the same list in
machine-readable form, and `SHA256SUMS` lets you check the downloads with `shasum -a 256 -c SHA256SUMS`.

Our changes to mpv are in `apple/patches/` (`libmpv_alkemyo.c`, `alkemyo_native_buffer.h` and the tvOS AVFoundation
audio patch). To rebuild the frameworks and use your own copy, follow `RELINK.md`.

| Component | Version | Licence | Release asset | SHA-256 | Upstream |
|---|---|---|---|---|---|
| FFmpeg | 8.1.2 | LGPL-2.1-or-later | `ffmpeg-8.1.2.tar.xz` | `464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c` | https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz |
| mpv | 0.41.0 (commit 41f6a645068483470267271e1d09966ca3b9f413) | LGPL-2.1-or-later | `mpv-41f6a645.tar.gz` | `068960e89211f2adc80af03f637fa393fb5e407d3dd23592c8fe8c5490bb7ae4` | https://github.com/mpv-player/mpv/archive/41f6a645068483470267271e1d09966ca3b9f413.tar.gz |
| libass | 0.17.5 | ISC | `libass-0.17.5.tar.xz` | `2dca25c0e0c837ddf00b52011b3f82cac1e4ddd3ad018227806b0c2288864acc` | https://github.com/libass/libass/releases/download/0.17.5/libass-0.17.5.tar.xz |
| FreeType | 2.14.3 | FTL | `freetype-2.14.3.tar.xz` | `36bc4f1cc413335368ee656c42afca65c5a3987e8768cc28cf11ba775e785a5f` | https://download.savannah.gnu.org/releases/freetype/freetype-2.14.3.tar.xz |
| HarfBuzz | 14.2.0 | MIT-Modern-Variant | `harfbuzz-14.2.0.tar.xz` | `94017020f96d025bb66ae91574e4cf334bcad23e8175a8a40565b3721bc2eaff` | https://github.com/harfbuzz/harfbuzz/releases/download/14.2.0/harfbuzz-14.2.0.tar.xz |
| FriBidi | 1.0.16 | LGPL-2.1-or-later | `fribidi-1.0.16.tar.xz` | `1b1cde5b235d40479e91be2f0e88a309e3214c8ab470ec8a2744d82a5a9ea05c` | https://github.com/fribidi/fribidi/releases/download/v1.0.16/fribidi-1.0.16.tar.xz |
| libunibreak | 6.1 | Zlib | `libunibreak-6.1.tar.gz` | `cc4de0099cf7ff05005ceabff4afed4c582a736abc38033e70fdac86335ce93f` | https://github.com/adah1972/libunibreak/releases/download/libunibreak_6_1/libunibreak-6.1.tar.gz |
| libplacebo | 7.360.1 | LGPL-2.1-or-later | `libplacebo-v7.360.1-with-submodules.tar.gz` | `697847d084a8817985ee9cf5c1e460d31230fbd064619963914f49321478df9b` | https://code.videolan.org/videolan/libplacebo/-/tree/v7.360.1 (commit cee9b076f2c63104ccfd497fa79c39a867293ec4, with submodules) |
| Little CMS | 2.17 | MIT | `lcms2-2.17.tar.gz` | `d11af569e42a1baa1650d20ad61d12e41af4fead4aa7964a01f93b08b53ab074` | https://github.com/mm2/Little-CMS/releases/download/lcms2.17/lcms2-2.17.tar.gz |
| libdovi (dovi_tool dolby_vision) | 3.3.2 | MIT | `dovi_tool-libdovi-3.3.2.tar.gz` | `8ccb1922d7dbb57bc4f2c15c10b90c462f7a5f292efe317c116db923728dd3f1` | https://github.com/quietvoid/dovi_tool/archive/refs/tags/libdovi-3.3.2.tar.gz |
| uchardet | 0.0.8 | MPL-1.1 | `uchardet-0.0.8.tar.xz` | `e97a60cfc00a1c147a674b097bb1422abd9fa78a2d9ce3f3fdcc2e78a34ac5f0` | https://www.freedesktop.org/software/uchardet/releases/uchardet-0.0.8.tar.xz |
| libbluray (with its bundled libudfread) | 1.4.0 | LGPL-2.1-or-later | `libbluray-1.4.0.tar.xz` | `77937baf07eadda4b2b311cf3af4c50269d2ea3165041f5843d96476c4c92777` | https://download.videolan.org/pub/videolan/libbluray/1.4.0/libbluray-1.4.0.tar.xz |

The libplacebo asset is the `v7.360.1` tag with its submodules included, because the tag archive on the project's site
leaves them empty and the build uses fast_float and glad from them. Submodule commits:
- `3rdparty/Vulkan-Headers`: `450bd2232225d6c7728a4108055ac2e37cef6475`
- `3rdparty/fast_float`: `97b54ca9e75f5303507699d27c6b4f4efe4641a1`
- `3rdparty/glad`: `73db193f853e2ee079bf3ca8a64aa2eaf6459043`
- `3rdparty/jinja`: `15206881c006c79667fe5154fe80c01c65410679`
- `3rdparty/markupsafe`: `297fc8e356e6836a62087949245d09a28e9f1b13`

libbluray's archive includes the libudfread copy it builds in (`contrib/libudfread`, LGPL 2.1 or later). libdovi is
Rust: its archive has the `dolby_vision` crate and its `Cargo.lock`; the crates it depends on come from crates.io.

## Prebuilt static libraries

The libraries other than FFmpeg and mpv are linked from MPVKit's prebuilt static archives, pinned by sha256 in
`apple/pins/prebuilt-dependencies.json`. Each was built from the upstream source above by the MPVKit recipe named here.

| Static library | Built by | Archive | SHA-256 |
|---|---|---|---|
| Libass | https://github.com/mpvkit/libass-build/tree/0.17.5 | https://github.com/mpvkit/libass-build/releases/download/0.17.5/Libass.xcframework.zip | `3f4c576d2818ceb4544aa2a20e1f55846511c5e706fd19adc3ea9fd842270498` |
| Libfreetype | https://github.com/mpvkit/libass-build/tree/0.17.5 | https://github.com/mpvkit/libass-build/releases/download/0.17.5/Libfreetype.xcframework.zip | `496ca62488530e14b1e4624d20ee2b237c0bd675cd70c19da578a5768302d02d` |
| Libharfbuzz | https://github.com/mpvkit/libass-build/tree/0.17.5 | https://github.com/mpvkit/libass-build/releases/download/0.17.5/Libharfbuzz.xcframework.zip | `aa8e0b9ca0387dac74e3e93c86e34d11982bb013b28022d0e6966a8427a35b2e` |
| Libfribidi | https://github.com/mpvkit/libass-build/tree/0.17.5 | https://github.com/mpvkit/libass-build/releases/download/0.17.5/Libfribidi.xcframework.zip | `bc15e097b892f2f90424e4a27ba287070cc2f98a74a4da10e6d2481d15cf5ff9` |
| Libunibreak | https://github.com/mpvkit/libass-build/tree/0.17.5 | https://github.com/mpvkit/libass-build/releases/download/0.17.5/Libunibreak.xcframework.zip | `940d9833cf4477d0a260d9f2b4066125bc0ff7bbc111ac3c90e774765b77a559` |
| Libplacebo | https://github.com/mpvkit/libplacebo-build/tree/7.360.1 | https://github.com/mpvkit/libplacebo-build/releases/download/7.360.1/Libplacebo.xcframework.zip | `2fa3d54cb81f302d6f11c7b2f509af30944381c3b11ee9d35096eb4637a6e2dd` |
| lcms2 | https://github.com/mpvkit/lcms2-build/tree/2.17.0 | https://github.com/mpvkit/lcms2-build/releases/download/2.17.0/lcms2.xcframework.zip | `dc0dce0606f6ab6841a8ec5a6bd4448e2f3ef00661a050460f806c9393dc6982` |
| Libdovi | https://github.com/mpvkit/libdovi-build/tree/3.3.2 | https://github.com/mpvkit/libdovi-build/releases/download/3.3.2/Libdovi.xcframework.zip | `e693e239808350868e79c5448ef9f02e2716bc822dd8632a41a368a1eae5ca7d` |
| Libuchardet | https://github.com/mpvkit/libuchardet-build/tree/0.0.8 | https://github.com/mpvkit/libuchardet-build/releases/download/0.0.8/Libuchardet.xcframework.zip | `ea4f548a230a755e059144657cc9e2ff563c1cdeae03974c38f8b6e1a40303fb` |
| Libbluray | https://github.com/mpvkit/libbluray-build/tree/1.4.0 | https://github.com/mpvkit/libbluray-build/releases/download/1.4.0/Libbluray.xcframework.zip | `bc037d34e2b0b5ab7f202fb371f5fb298136cc66fdf406c2172185d06f53f18d` |
