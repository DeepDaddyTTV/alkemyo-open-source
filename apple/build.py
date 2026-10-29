#!/usr/bin/env python3
"""Build AlkemyoFFmpeg and AlkemyoMPV for iPhone and iPad (ios) or Apple TV (tvos) from the pinned sources.

    python3 apple/build.py tvos --work ~/alkemyo-work --tools ~/alkemyo-tools

Writes output/<platform>/AlkemyoFFmpeg.xcframework, AlkemyoMPV.xcframework and their build receipts
(ffmpeg-build.json, mpv-build.json). --tools is a folder with bin/meson, bin/ninja and bin/pkg-config
(meson 1.4.2, ninja 1.13.0, pkgconf 3.0.7). The mpv source archive is downloaded from GitHub and checked
against apple/pins/mpv-source-pin.json unless --archive gives a local copy. No signing. See RELINK.md.
"""
import argparse, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import apple_player


def mpv_archive(given):
    pin = json.loads((apple_player.ROOT / 'apple/pins/mpv-source-pin.json').read_text())
    archive = given or apple_player.CACHE / ('mpv-' + pin['commit'][:8] + '.tar.gz')
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        apple_player.run(['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '3',
                          'https://github.com/mpv-player/mpv/archive/' + pin['commit'] + '.tar.gz', '-o', archive])
    if apple_player.digest(archive) != pin['sha256']: raise RuntimeError('mpv source checksum mismatch: ' + str(archive))
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('platform', choices=sorted(apple_player.PLATFORMS))
    parser.add_argument('--work', type=pathlib.Path, required=True, help='a build folder whose path has no spaces')
    parser.add_argument('--tools', type=pathlib.Path, required=True, help='folder with bin/meson, bin/ninja and bin/pkg-config')
    parser.add_argument('--archive', type=pathlib.Path, help='a local copy of the pinned mpv source archive')
    parser.add_argument('--sdk', action='append', help='build only these SDKs (default: device and simulator)')
    args = parser.parse_args()
    platform = args.platform; work = args.work.absolute()
    sdks = args.sdk or list(apple_player.PLATFORMS[platform]['sdks'])
    unknown = [s for s in sdks if s not in apple_player.PLATFORMS[platform]['sdks']]
    if unknown: parser.error('unknown SDK for ' + platform + ': ' + ', '.join(unknown))
    out = apple_player.ROOT / apple_player.PLATFORMS[platform]['output']
    apple_player.build_ffmpeg_xcframework(platform, work / 'ffmpeg', sdks)
    archive = mpv_archive(args.archive.absolute() if args.archive else None)
    evidence = work / 'mpv-evidence'
    frameworks, slices = [], []
    for sdk in sdks:
        framework, receipt = apple_player.build_mpv(platform, sdk, work / 'mpv', archive, args.tools, evidence)
        frameworks.append(framework); slices.append(receipt)
    apple_player.xcframework(frameworks, out / 'AlkemyoMPV.xcframework')
    (out / 'mpv-build.json').write_text(json.dumps({'schema': 2, 'framework': 'AlkemyoMPV', 'slices': slices}, indent=2) + '\n')
    print(out / 'AlkemyoFFmpeg.xcframework'); print(out / 'AlkemyoMPV.xcframework')


if __name__ == '__main__':
    main()
