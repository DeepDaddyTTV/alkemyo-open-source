#!/usr/bin/env python3
"""Build the LGPL player runtime that the Linux .deb ships in /opt/alkemyo/lib (licensing L04).

FFmpeg, libmpv, libplacebo and dav1d are compiled from the checksum-pinned sources in
scripts/linux-player-sources.json and installed with RPATH $ORIGIN, so alkemyo never
loads a distribution libmpv or FFmpeg (those are GPL builds on Ubuntu, Mint and
elementary OS). The build fails unless FFmpeg reports "LGPL version 2.1 or later",
mpv was configured with -Dgpl=false, and every NEEDED library is either bundled here
or an allowed system library. Licence texts and a build record go next to the libraries.
Build on the oldest supported glibc (Ubuntu 22.04) so the result runs on newer ones.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "scripts/linux-player-sources.json"
# NEEDED entries a bundled library may have that come from the system. Every one is
# LGPL-2.1+-compatible as a dynamic dependency; gnutls brings nettle/gmp (LGPLv3+ or
# GPLv2+), whose texts ship in the notices.
SYSTEM_NEEDED = re.compile(r"^(libc|libm|libdl|libpthread|librt|libgcc_s|libstdc\+\+|ld-linux[-a-z0-9_]*|libz|libgnutls|libass|liblcms2|libuchardet|libbluray"
                           r"|libva|libva-drm|libva-x11|libdrm|libpulse|libpipewire-0\.3|libasound|libX11|libXext|libXrandr|libXpresent|libXss|libXinerama|libEGL|libGL|libGLX"
                           r"|libfreetype|libfribidi|libharfbuzz|libfontconfig|libxml2)\.so(\.[0-9]+)*$")
LGPL = "LGPL version 2.1 or later"
DOWNLOAD = False


class PlayerBuildError(Exception):
    pass


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(command, cwd=None, env=None, log=None):
    with Path(log).open("a") as output:
        output.write("$ " + " ".join(map(str, command)) + "\n"); output.flush()
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise PlayerBuildError(f"{command[0]} failed ({result.returncode}); see {log}")


def check_options(spec):
    """The recipe itself must keep the licence rules; a test reads this too."""
    configure = spec["ffmpeg_configure"]
    for flag in configure["forbidden"]:
        if flag in configure["required"]:
            raise PlayerBuildError("FFmpeg flag is both required and forbidden: " + flag)
    if "-Dgpl=false" not in spec["mpv_options"]["required"]:
        raise PlayerBuildError("mpv must be built with -Dgpl=false")


def unpack(spec, name, sources, work):
    entry = spec["sources"][name]
    archive = Path(sources) / Path(entry["mirror"]).name
    if not archive.is_file() and DOWNLOAD:
        Path(sources).mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "3", "-o", str(archive) + ".part", entry["mirror"]], check=True)
        os.replace(str(archive) + ".part", archive)
    if not archive.is_file():
        raise PlayerBuildError(f"Missing source archive {archive.name}; download {entry['mirror']}")
    if digest(archive) != entry["sha256"]:
        raise PlayerBuildError("Source checksum mismatch: " + archive.name)
    destination = work / "src" / name
    shutil.rmtree(destination, ignore_errors=True); destination.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        roots = {m.name.split("/", 1)[0] for m in tar.getmembers()}
        if len(roots) != 1:
            raise PlayerBuildError("Source archive has more than one top folder: " + archive.name)
        tar.extractall(destination, filter="data")
    return destination / roots.pop()


def needed(library):
    out = subprocess.run(["readelf", "-d", str(library)], capture_output=True, text=True, check=True).stdout
    return re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", out), re.findall(r"\((?:RUNPATH|RPATH)\)\s+Library (?:runpath|rpath): \[([^\]]+)\]", out)


def verify(spec, lib):
    """Licence and linkage checks on the installed libraries."""
    bundled = {}
    for path in sorted(lib.glob("*.so*")):
        stem = path.name.split(".so", 1)[0]
        if stem not in spec["bundled"]:
            raise PlayerBuildError("Unexpected library in the runtime: " + path.name)
        bundled[path.name] = path
    missing = set(spec["bundled"]) - {n.split(".so", 1)[0] for n in bundled}
    if missing:
        raise PlayerBuildError("Runtime is missing " + ", ".join(sorted(missing)))
    sonames = {p.name for p in lib.glob("*.so*")}
    for name, path in bundled.items():
        libs, paths = needed(path)
        if paths != ["$ORIGIN"]:
            raise PlayerBuildError(f"{name} must have RUNPATH $ORIGIN, has {paths}")
        for dependency in libs:
            stem = dependency.split(".so", 1)[0]
            if any(stem == f for f in spec["forbidden_needed"]):
                raise PlayerBuildError(f"{name} links forbidden {dependency}")
            if dependency not in sonames and not SYSTEM_NEEDED.match(dependency):
                raise PlayerBuildError(f"{name} links unlisted system library {dependency}")
    return bundled


def ffmpeg_licence(lib):
    """avcodec_license() from the built library, read in a child so this process loads nothing."""
    probe = ("import ctypes,sys;a=ctypes.CDLL(sys.argv[1]);a.avcodec_license.restype=ctypes.c_char_p;"
             "a.avcodec_configuration.restype=ctypes.c_char_p;print(a.avcodec_license().decode());print(a.avcodec_configuration().decode())")
    avcodec = next(p for p in lib.glob("libavcodec.so.*") if not p.is_symlink())
    out = subprocess.run([sys.executable, "-I", "-c", probe, str(avcodec)], capture_output=True, text=True, check=True,
                         env={**os.environ, "LD_LIBRARY_PATH": str(lib)}).stdout.splitlines()
    return out[0], out[1] if len(out) > 1 else ""


def build(sources, output, jobs=None):
    spec = json.loads(SPEC.read_text())
    check_options(spec)
    output = Path(output).resolve()
    work = output.parent / (output.name + ".work")
    shutil.rmtree(work, ignore_errors=True); shutil.rmtree(output, ignore_errors=True)
    prefix = work / "prefix"; log = work / "build.log"; prefix.mkdir(parents=True)
    jobs = str(jobs or os.cpu_count() or 2)
    tools = work / "tools"
    subprocess.run([sys.executable, "-m", "venv", str(tools)], check=True)
    run([tools / "bin/pip", "install", "--disable-pip-version-check", "--no-cache-dir", *spec["python"]], log=log)
    env = {**os.environ, "PATH": f"{tools / 'bin'}:{os.environ['PATH']}",
           "PKG_CONFIG_PATH": str(prefix / "lib/pkgconfig"), "LDFLAGS": "-Wl,-rpath,'$ORIGIN' -Wl,--enable-new-dtags",
           "CFLAGS": "-O2 -fstack-protector-strong -D_FORTIFY_SOURCE=2", "PYTHONNOUSERSITE": "1"}
    meson = [tools / "bin/meson", "setup", "--prefix", prefix, "--libdir", "lib", "--buildtype", "release", "-Ddefault_library=shared"]

    def meson_build(name, options):
        source = unpack(spec, name, sources, work)
        build_dir = work / "build" / name
        run([*meson, *options, build_dir, source], env=env, log=log)
        run([tools / "bin/ninja", "-C", build_dir, "-j", jobs, "install"], env=env, log=log)
        return source

    trees = {"dav1d": meson_build("dav1d", ["-Denable_tools=false", "-Denable_tests=false"])}
    trees["ffmpeg"] = source = unpack(spec, "ffmpeg", sources, work)
    run(["./configure", f"--prefix={prefix}", "--libdir=" + str(prefix / "lib"), *spec["ffmpeg_configure"]["required"],
         "--extra-ldflags=-Wl,-rpath,'$$ORIGIN' -Wl,--enable-new-dtags"], cwd=source, env=env, log=log)
    config = (source / "config.h").read_text()
    if f'#define FFMPEG_LICENSE "{LGPL}"' not in config:
        raise PlayerBuildError("FFmpeg configure did not report " + LGPL)
    run(["make", "-j", jobs, "install"], cwd=source, env=env, log=log)
    trees["libplacebo"] = meson_build("libplacebo", spec["libplacebo_options"])
    trees["mpv"] = meson_build("mpv", spec["mpv_options"]["required"])

    # Each library is shipped once, under its SONAME (the name NEEDED entries use); no symlinks, so the tar and
    # .deb hold only regular files and the unversioned development links are not shipped.
    lib = output / "lib"; lib.mkdir(parents=True)
    for path in sorted((prefix / "lib").glob("*.so*")):
        if path.is_symlink():
            continue
        soname = re.findall(r"\(SONAME\)\s+Library soname: \[([^\]]+)\]", subprocess.run(["readelf", "-d", str(path)], capture_output=True, text=True, check=True).stdout)
        if len(soname) != 1 or "/" in soname[0] or (lib / soname[0]).exists():
            raise PlayerBuildError("Library has no single SONAME: " + path.name)
        shutil.copy2(path, lib / soname[0]); subprocess.run(["strip", "--strip-unneeded", str(lib / soname[0])], check=True)
    bundled = verify(spec, lib)
    licence, configuration = ffmpeg_licence(lib)
    if licence != LGPL:
        raise PlayerBuildError("Built FFmpeg reports " + licence)
    for flag in spec["ffmpeg_configure"]["forbidden"]:
        if flag in configuration.split():
            raise PlayerBuildError("Built FFmpeg was configured with " + flag)
    mpv_config = (work / "build/mpv/meson-info/intro-buildoptions.json")
    options = {o["name"]: o["value"] for o in json.loads(mpv_config.read_text())}
    if options.get("gpl") is not False:
        raise PlayerBuildError("mpv was not configured with gpl=false")

    licences = output / "licenses"; licences.mkdir()
    for name, tree in trees.items():
        for notice in spec["sources"][name]["notices"]:
            shutil.copy2(tree / notice, licences / f"{name}-{notice.replace('/', '-')}.txt")
    glibc = max((tuple(map(int, v.split("."))) for p in bundled.values()
                 for v in re.findall(r"GLIBC_([0-9.]+)", subprocess.run(["objdump", "-T", str(p)], capture_output=True, text=True, check=True).stdout)),
                default=(0,))
    record = {"schema": 1, "builder_sha256": digest(__file__), "spec_sha256": digest(SPEC), "machine": platform.machine(),
              "ffmpeg_license": licence, "ffmpeg_configuration": configuration, "mpv_gpl": False,
              "minimum_glibc": ".".join(map(str, glibc)),
              "sources": {n: {"version": s["version"], "licence": s["licence"], "sha256": s["sha256"], "url": s["url"]} for n, s in spec["sources"].items()},
              "libraries": {n: {"sha256": digest(p), "needed": needed(p)[0]} for n, p in sorted(bundled.items())}}
    (output / "player-build.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sources", required=True, help="folder holding the pinned source archives (mirror file names)")
    parser.add_argument("--output", required=True, help="new folder for lib/, licenses/ and player-build.json")
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--download", action="store_true", help="fetch missing archives from their mirror (still checked by sha256)")
    args = parser.parse_args(argv)
    global DOWNLOAD
    DOWNLOAD = args.download
    try:
        record = build(args.sources, args.output, args.jobs)
    except PlayerBuildError as error:
        print("error: " + str(error), file=sys.stderr); return 1
    print(json.dumps({"ffmpeg_license": record["ffmpeg_license"], "minimum_glibc": record["minimum_glibc"], "libraries": sorted(record["libraries"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
