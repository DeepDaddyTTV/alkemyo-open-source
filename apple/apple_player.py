"""Builder for alkemyo's LGPL media frameworks on iPhone, iPad and Apple TV.

Two separate dynamic frameworks per Apple platform, each with its own install name:

    AlkemyoFFmpeg    FFmpeg compiled from the pinned source, LGPL 2.1 (no version3, no GPL, Apple's TLS)
    AlkemyoMPV       mpv compiled from the pinned source (-Dgpl=false) with only the allow-listed prebuilt static
                     libraries, linked to AlkemyoFFmpeg

apple/pins/apple-player-allowlist.json is the list of what may be linked; every framework is checked against it
(otool -L and nm) before it is written. apple/build.py is the command-line entry point; see RELINK.md.
Builds need macOS with Xcode, and for AlkemyoMPV meson, ninja and pkg-config.
"""
import hashlib, json, os, pathlib, plistlib, re, shutil, subprocess, tarfile, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Downloaded, checksum-pinned inputs and the FFmpeg source tree (no spaces allowed: FFmpeg's configure rejects them).
CACHE = pathlib.Path(os.environ.get('ALKEMYO_PLAYER_CACHE', str(ROOT / 'cache')))
ALLOWLIST = ROOT / 'apple/pins/apple-player-allowlist.json'

PLATFORMS = {
    'ios': {'output': 'output/ios', 'minimum': '17.0', 'zip_platform': 'ios',
            'sdks': {'iphoneos': {'variant': None, 'slice': 'ios-arm64', 'target': 'arm64-apple-ios17.0', 'plist': 'iPhoneOS'},
                     'iphonesimulator': {'variant': 'simulator', 'slice': 'ios-arm64-simulator', 'target': 'arm64-apple-ios17.0-simulator', 'plist': 'iPhoneSimulator'}}},
    'tvos': {'output': 'output/tvos', 'minimum': '18.0', 'zip_platform': 'tvos',
             'sdks': {'appletvos': {'variant': None, 'slice': 'tvos-arm64', 'target': 'arm64-apple-tvos18.0', 'plist': 'AppleTVOS'},
                      'appletvsimulator': {'variant': 'simulator', 'slice': 'tvos-arm64-simulator', 'target': 'arm64-apple-tvos18.0-simulator', 'plist': 'AppleTVSimulator'}}},
}
FFMPEG_FRAMEWORKS = ['AudioToolbox', 'AVFoundation', 'CoreAudio', 'CoreFoundation', 'CoreGraphics', 'CoreImage', 'CoreMedia',
                     'CoreVideo', 'Foundation', 'IOSurface', 'Metal', 'QuartzCore', 'Security', 'VideoToolbox']


def allowlist():
    return json.loads(ALLOWLIST.read_text())


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def run(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def output(args):
    return subprocess.check_output([str(a) for a in args], text=True)


def write_changed(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != data: path.write_bytes(data)


def sdk_path(sdk):
    return output(['xcrun', '--sdk', sdk, '--show-sdk-path']).strip()


def framework_dir(platform, name, slice_name):
    return ROOT / PLATFORMS[platform]['output'] / (name + '.xcframework') / slice_name / (name + '.framework')


# Required-reason APIs each framework calls, for its App Store privacy manifest: FFmpeg's and mpv's file access stats
# files for the app (0A2A.1, a third-party wrapper), mpv's timers read mach_absolute_time (35F9.1).
PRIVACY = {'AlkemyoFFmpeg': [('NSPrivacyAccessedAPICategoryFileTimestamp', '0A2A.1')],
           'AlkemyoMPV': [('NSPrivacyAccessedAPICategoryFileTimestamp', '0A2A.1'), ('NSPrivacyAccessedAPICategorySystemBootTime', '35F9.1')]}


def info_plist(framework, name, identifier, platform, sdk):
    (framework / 'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps({
        'NSPrivacyTracking': False, 'NSPrivacyTrackingDomains': [], 'NSPrivacyCollectedDataTypes': [],
        'NSPrivacyAccessedAPITypes': [{'NSPrivacyAccessedAPIType': t, 'NSPrivacyAccessedAPITypeReasons': [r]} for t, r in PRIVACY[name]]}))
    (framework / 'Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': identifier, 'CFBundleExecutable': name, 'CFBundleName': name, 'CFBundlePackageType': 'FMWK',
        'CFBundleVersion': '1', 'CFBundleShortVersionString': '0.1', 'MinimumOSVersion': PLATFORMS[platform]['minimum'],
        'CFBundleSupportedPlatforms': [PLATFORMS[platform]['sdks'][sdk]['plist']]}))


# ---- Pinned MPVKit archives (allow-listed static libraries and headers only) ----

def pinned(name):
    manifest = json.loads((ROOT / 'apple/pins/prebuilt-dependencies.json').read_text())
    return next(d for d in manifest['dependencies'] if d['name'] == name)


def fetch(dep):
    archive = CACHE / (dep['name'] + '.xcframework.zip')
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        run(['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '3', dep['url'], '-o', archive])
    if digest(archive) != dep['sha256']: raise RuntimeError('Pinned archive checksum mismatch: ' + dep['name'])
    return archive


def archive_entry(z, name, platform, variant):
    info = plistlib.loads(z.read(name + '.xcframework/Info.plist'))
    return next(e for e in info['AvailableLibraries'] if e['SupportedPlatform'] == PLATFORMS[platform]['zip_platform']
                and e.get('SupportedPlatformVariant') == variant and 'arm64' in e['SupportedArchitectures'])


def extract_static(name, platform, sdk, directory):
    """The arm64 static library of one allow-listed archive, thinned and cached by archive digest."""
    dep = pinned(name); variant = PLATFORMS[platform]['sdks'][sdk]['variant']
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / (name + '.a'); record = directory / (name + '.cache.json')
    with zipfile.ZipFile(fetch(dep)) as z:
        entry = archive_entry(z, name, platform, variant)
        expected = {'archive_sha256': dep['sha256'], 'slice': entry['LibraryIdentifier']}
        cached = json.loads(record.read_text()) if record.exists() else {}
        if not library.exists() or any(cached.get(k) != v for k, v in expected.items()) or cached.get('binary_sha256') != digest(library):
            prefix = name + '.xcframework/'
            binary = prefix + entry['LibraryIdentifier'] + '/' + entry.get('BinaryPath', entry['LibraryPath'] + '/' + name)
            fat = directory / (name + '.fat.a'); fat.write_bytes(z.read(binary))
            if output(['lipo', '-archs', fat]).split() == ['arm64']: fat.replace(library)
            else:
                run(['lipo', fat, '-thin', 'arm64', '-output', library]); fat.unlink()
            record.write_text(json.dumps(dict(expected, binary_sha256=digest(library))) + '\n')
    return library, dict(dep, slice=expected['slice'], binary_sha256=digest(library))


def extract_headers(name, platform, sdk, include, subdirectory):
    dep = pinned(name); variant = PLATFORMS[platform]['sdks'][sdk]['variant']
    with zipfile.ZipFile(fetch(dep)) as z:
        entry = archive_entry(z, name, platform, variant)
        prefix = name + '.xcframework/' + entry['LibraryIdentifier'] + '/' + entry['LibraryPath'] + '/Headers/'
        for item in z.namelist():
            if not item.startswith(prefix) or not item.endswith('.h'): continue
            relative = pathlib.PurePosixPath(subdirectory) / item[len(prefix):]
            if relative.is_absolute() or '..' in relative.parts: raise RuntimeError('Unsafe header path: ' + item)
            write_changed(include / relative, z.read(item))


# ---- Checks shared by every framework ----

def linked_paths(binary):
    lines = output(['otool', '-L', binary]).splitlines()[1:]
    return [line.strip().split(' (')[0] for line in lines if line.strip()]


def check_binary(binary, name, required_symbols=(), forbidden_symbols=()):
    """Fails unless the binary links only its allow-listed frameworks and system libraries, and none of the
    forbidden libraries' symbols (gnutls, gmp, nettle, OpenSSL, LuaJIT, Vulkan, shaderc, dav1d, uavs3d) are in it."""
    rules = allowlist(); own = '@rpath/' + name + '.framework/' + name
    allowed = ['@rpath/' + other + '.framework/' + other for other in rules['frameworks'][name]['links']]
    problems = []
    for path in linked_paths(binary):
        if path == own or path in allowed or any(path.startswith(p) for p in rules['system_link_prefixes']): continue
        problems.append('links ' + path)
    symbols = output(['nm', '-g', '-j', binary]).split()
    defined = set(output(['nm', '-g', '-U', '-j', binary]).split())
    for prefix in rules['forbidden_symbol_prefixes']:
        hits = [s for s in symbols if s.startswith(prefix)]
        if hits: problems.append('has ' + prefix + '* symbols, e.g. ' + hits[0])
    for symbol in required_symbols:
        if symbol not in defined: problems.append('does not define ' + symbol)
    for symbol in forbidden_symbols:
        if symbol in defined: problems.append('defines ' + symbol)
    if problems: raise RuntimeError(name + ' failed the allow-list check:\n  ' + '\n  '.join(problems))
    return {'load_commands': output(['otool', '-L', binary]), 'sha256': digest(binary), 'size': binary.stat().st_size}


# ---- AlkemyoFFmpeg ----

def ffmpeg_spec():
    return json.loads((ROOT / 'apple/pins/ffmpeg-source.json').read_text())['ffmpeg']


def ffmpeg_options(source, prefix, flags):
    options = [str(source / 'configure'), '--prefix=' + str(prefix), '--arch=aarch64',
               '--target-os=darwin', '--enable-cross-compile', '--cc=clang', '--cxx=clang++',
               '--enable-static', '--disable-shared', '--enable-pic',
               '--disable-gpl', '--disable-nonfree', '--disable-autodetect', '--disable-doc',
               '--disable-debug', '--disable-programs', '--disable-indevs', '--disable-outdevs',
               '--enable-network', '--enable-securetransport', '--enable-videotoolbox',
               '--enable-audiotoolbox', '--extra-cflags=' + flags, '--extra-ldflags=' + flags]
    rules = allowlist()['ffmpeg_configure']
    missing = [o for o in rules['required'] if o not in options]
    forbidden = [o for o in options if o in rules['forbidden']]
    if missing or forbidden: raise RuntimeError('FFmpeg configure line breaks the allow-list: ' + str(missing + forbidden))
    return options


def build_ffmpeg(directory, sdkpath, target):
    """FFmpeg's static libraries for one slice, LGPL 2.1, with Apple's TLS, VideoToolbox and AudioToolbox."""
    spec = ffmpeg_spec()
    archive = CACHE / 'ffmpeg-expanded/downloads' / ('ffmpeg-' + spec['version'] + '.tar.xz')
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        run(['curl', '--fail', '--location', '--silent', '--show-error', spec['url'], '-o', archive])
    if digest(archive) != spec['sha256']: raise RuntimeError('FFmpeg source checksum mismatch')
    source_root = CACHE / 'ffmpeg-expanded/sources' / ('ffmpeg-' + spec['sha256'][:16])
    source = source_root / ('ffmpeg-' + spec['version'])
    if not (source / 'configure').exists():
        source_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar: tar.extractall(source_root, filter='data')
    build = directory / 'ffmpeg-build'; build.mkdir(parents=True, exist_ok=True)
    prefix = directory / 'ffmpeg-install'
    options = ffmpeg_options(source, prefix, '-target ' + target + ' -isysroot ' + sdkpath)
    fingerprint = {'source': spec, 'command': options}
    record = build / 'inputs.json'
    names = allowlist()['frameworks']['AlkemyoFFmpeg']['libraries']
    libraries = {n: prefix / 'lib' / ('lib' + n + '.a') for n in names}
    if not record.exists() or json.loads(record.read_text()) != fingerprint or not all(p.exists() for p in libraries.values()):
        env = dict(os.environ); env.pop('MACOSX_DEPLOYMENT_TARGET', None)
        for name, command in [('configure', options), ('make', ['make', '-j6']), ('install', ['make', 'install'])]:
            with (build / (name + '.log')).open('w') as log:
                run(command, cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT)
        record.write_text(json.dumps(fingerprint, indent=2) + '\n')
    licence = re.search(r'#define FFMPEG_LICENSE "([^"]+)"', (build / 'config.h').read_text())
    expected = allowlist()['frameworks']['AlkemyoFFmpeg']['licence']
    if not licence or licence.group(1) != expected:
        raise RuntimeError('FFmpeg licence is ' + (licence.group(1) if licence else 'unknown') + ', expected ' + expected)
    fingerprint['licence'] = licence.group(1)
    fingerprint['libraries'] = {n: digest(p) for n, p in libraries.items()}
    return libraries, prefix / 'include', fingerprint


def ffmpeg_framework(platform, sdk, directory):
    """One AlkemyoFFmpeg.framework: every FFmpeg static library force-loaded into one dylib, with its headers."""
    slice_info = PLATFORMS[platform]['sdks'][sdk]; sdkpath = sdk_path(sdk); target = slice_info['target']
    libraries, include, record = build_ffmpeg(directory, sdkpath, target)
    framework = directory / 'AlkemyoFFmpeg.framework'; framework.mkdir(parents=True, exist_ok=True)
    binary = framework / 'AlkemyoFFmpeg'
    command = ['xcrun', '--sdk', sdk, 'clang', '-target', target, '-isysroot', sdkpath, '-dynamiclib',
               '-Wl,-install_name,@rpath/AlkemyoFFmpeg.framework/AlkemyoFFmpeg', '-Wl,-dead_strip_dylibs', '-o', str(binary)]
    command += ['-Wl,-force_load,' + str(p) for p in libraries.values()]
    for name in FFMPEG_FRAMEWORKS: command += ['-framework', name]
    command += ['-lz', '-lbz2', '-liconv']
    with (directory / 'ffmpeg-link.log').open('w') as log: run(command, stdout=log, stderr=subprocess.STDOUT)
    shutil.copytree(include, framework / 'Headers', dirs_exist_ok=True)
    info_plist(framework, 'AlkemyoFFmpeg', allowlist()['frameworks']['AlkemyoFFmpeg']['identifier'], platform, sdk)
    checked = check_binary(binary, 'AlkemyoFFmpeg', required_symbols=['_avformat_open_input', '_avcodec_send_packet', '_avutil_license'])
    run(['codesign', '--force', '--sign', '-', framework])
    return framework, dict(record, sdk=sdk, target=target, link_command=command, **checked)


def xcframework(frameworks, destination):
    if destination.exists(): shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = ['xcodebuild', '-create-xcframework']
    for framework in frameworks: command += ['-framework', str(framework)]
    run(command + ['-output', str(destination)])


def build_ffmpeg_xcframework(platform, work, sdks=None):
    if any(c.isspace() for c in str(work)): raise ValueError('FFmpeg build cache path must not contain whitespace')
    frameworks, records = [], []
    for sdk in (sdks or PLATFORMS[platform]['sdks']):
        framework, record = ffmpeg_framework(platform, sdk, work / sdk)
        frameworks.append(framework); records.append(record)
    out = ROOT / PLATFORMS[platform]['output']
    xcframework(frameworks, out / 'AlkemyoFFmpeg.xcframework')
    receipt = {'schema': 2, 'framework': 'AlkemyoFFmpeg', 'builder_sha256': digest(__file__),
               'allowlist_sha256': digest(ALLOWLIST), 'ffmpeg_source': ffmpeg_spec(), 'minimum_os': PLATFORMS[platform]['minimum'],
               'slices': records}
    (out / 'ffmpeg-build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


# ---- AlkemyoMPV ----

MPV_COMMIT = '41f6a645068483470267271e1d09966ca3b9f413'
MPV_SHA = '068960e89211f2adc80af03f637fa393fb5e407d3dd23592c8fe8c5490bb7ae4'
AUDIO_PATCH_SHA = '693e8ace8057ac46c42195949777159c5aa37f9b7ce81f488758481973da9312'
MPV_OPTIONS = ['-Dlibmpv=true', '-Dcplayer=false', '-Dgpl=false', '-Dbuildtype=release', '-Db_lundef=true', '-Dauto_features=disabled',
               '-Dgl=enabled', '-Dplain-gl=enabled', '-Dios-gl=enabled', '-Dvideotoolbox-gl=disabled', '-Dvideotoolbox-pl=disabled',
               '-Dswift-build=disabled', '-Daudiounit=enabled', '-Davfoundation=enabled', '-Dcoreaudio=disabled', '-Dlua=disabled',
               '-Diconv=enabled', '-Duchardet=enabled', '-Dlibbluray=enabled', '-Dlcms2=enabled', '-Dzlib=enabled', '-Dlibavdevice=enabled']


def prepare_mpv_source(work, archive):
    """The pinned mpv source with alkemyo's mpv-side glue (libmpv_alkemyo.c, LGPL with mpv) and the tvOS audio patch."""
    if digest(archive) != MPV_SHA: raise RuntimeError('mpv source checksum mismatch')
    source = work / ('mpv-' + MPV_COMMIT)
    if not source.exists():
        with tarfile.open(archive) as tar: tar.extractall(work, filter='data')
    for path in allowlist()['mpv_overlay']: shutil.copy2(ROOT / path, source / 'video/out' / pathlib.Path(path).name)

    def replace(file, before, after):
        p = source / file; s = p.read_text()
        if after not in s:
            if before not in s: raise RuntimeError('mpv source changed: ' + file)
            p.write_text(s.replace(before, after, 1))
    replace('video/out/vo_libmpv.c', 'const struct render_backend_fns *render_backends[] = {',
            'extern const struct render_backend_fns render_backend_alkemyo;\nconst struct render_backend_fns *render_backends[] = {\n    &render_backend_alkemyo,')
    replace('video/out/vo_libmpv.c', '    vo->hwdec_devs = ctx->hwdec_devs;',
            "    if (ctx->renderer->fns == &render_backend_alkemyo) {\n        struct vo_driver *native_driver = talloc_memdup(vo, vo->driver, sizeof(*native_driver));\n"
            "        native_driver->caps = ctx->renderer->driver_caps;\n        vo->driver = native_driver;\n    }\n    vo->hwdec_devs = ctx->hwdec_devs;")
    replace('meson.build', "    'video/out/libmpv_sw.c',", "    'video/out/libmpv_sw.c',\n    'video/out/libmpv_alkemyo.c',")
    replace('meson.build', "# Keeps track of all enabled/disabled features",
            "dependencies += dependency('appleframeworks', modules: ['OpenGLES'])\n# Keeps track of all enabled/disabled features")
    replace('meson.build', "libmpv = library('mpv',", "libmpv = library('AlkemyoMPV',")
    patch = ROOT / 'apple/patches/0003-enable-avfoundation-ao-tvos.patch'
    if digest(patch) != AUDIO_PATCH_SHA: raise RuntimeError('audio patch checksum mismatch')
    if not (source / '.alkemyo-audio-patched').exists():
        run(['patch', '-p1', '-i', patch], cwd=source); (source / '.alkemyo-audio-patched').touch()
    audio = source / 'audio/out/ao_avfoundation.m'
    if 'AlkemyoNativeMPVAVObserver' not in audio.read_text():
        audio.write_text(re.sub(r'\bAVObserver\b', 'AlkemyoNativeMPVAVObserver', audio.read_text()))
    return source


def ffmpeg_version(include, name):
    header = ''.join(p.read_text() for p in (include / name).glob('version*.h')); parts = []
    for suffix in ['MAJOR', 'MINOR', 'MICRO']:
        match = re.search(r'#define\s+' + name.upper() + r'_VERSION_' + suffix + r'\s+(\d+)', header)
        if not match: raise RuntimeError('FFmpeg header version missing: ' + name)
        parts.append(match.group(1))
    return '.'.join(parts)


def build_mpv(platform, sdk, work, archive, tools, evidence):
    """AlkemyoMPV.framework for one slice: mpv from source, the allow-listed static libraries, AlkemyoFFmpeg."""
    work = work.absolute(); work.mkdir(parents=True, exist_ok=True)
    if any(c.isspace() for c in str(work)): raise ValueError('Use a private work path without spaces')
    slice_info = PLATFORMS[platform]['sdks'][sdk]; target = slice_info['target']; sdkpath = sdk_path(sdk)
    source = prepare_mpv_source(work, archive)
    ffmpeg = framework_dir(platform, 'AlkemyoFFmpeg', slice_info['slice'])
    if not (ffmpeg / 'AlkemyoFFmpeg').exists(): raise RuntimeError('Build AlkemyoFFmpeg first: ' + str(ffmpeg))
    # meson links against a private copy, so the xcframework is never written by this step.
    linkdir = work / (sdk + '-ffmpeg'); linkdir.mkdir(exist_ok=True)
    shutil.copytree(ffmpeg, linkdir / 'AlkemyoFFmpeg.framework', symlinks=True, dirs_exist_ok=True)
    ffinclude = linkdir / 'AlkemyoFFmpeg.framework/Headers'
    include = work / (sdk + '-include'); libs = work / (sdk + '-libs'); pc = work / (sdk + '-pkgconfig')
    for d in [include, libs, pc]: d.mkdir(exist_ok=True)
    rules = allowlist(); archives = {}; records = []
    for entry in rules['mpv_archives']:
        archives[entry['name']], record = extract_static(entry['name'], platform, sdk, libs); records.append(record)
        if entry.get('headers') is not None: extract_headers(entry['name'], platform, sdk, include, entry['headers'])
    if (include / 'uchardet/uchardet.h').exists(): shutil.copy2(include / 'uchardet/uchardet.h', include / 'uchardet.h')
    cflags = '-I' + str(include) + ' -I' + str(include / 'uchardet')
    for entry in rules['mpv_archives']:
        if 'pkg' not in entry: continue
        link = ' '.join(str(archives[n]) for n in entry['link']) + ' ' + ' '.join(entry['system'])
        (pc / (entry['pkg'] + '.pc')).write_text('Name: ' + entry['pkg'] + '\nDescription: allow-listed static ' + entry['name'] +
                                                 '\nVersion: ' + entry['version'] + '\nLibs: ' + link + '\nCflags: ' + cflags + '\n')
    for name in rules['frameworks']['AlkemyoFFmpeg']['libraries']:
        lib = 'lib' + name
        (pc / (lib + '.pc')).write_text('Name: ' + lib + '\nDescription: AlkemyoFFmpeg.framework\nVersion: ' + ffmpeg_version(ffinclude, lib) +
                                        '\nLibs: -F' + str(linkdir) + ' -framework AlkemyoFFmpeg\nCflags: -I' + str(ffinclude) + '\n')
    tools = tools.absolute()
    env = dict(os.environ, PYTHONPATH=str(tools), PATH=str(tools / 'bin') + ':' + os.environ['PATH'], PKG_CONFIG_LIBDIR=str(pc))
    env.pop('MACOSX_DEPLOYMENT_TARGET', None)
    flags = ['-target', target, '-isysroot', sdkpath]
    linkflags = flags + ['-framework', 'OpenGLES', '-framework', 'CoreVideo', '-framework', 'VideoToolbox', '-framework', 'CoreMedia',
                         '-framework', 'IOSurface', '-Wl,-rpath,@loader_path/..', '-Wl,-dead_strip_dylibs']
    cross = work / (sdk + '.ini')
    cross.write_text("[binaries]\nc = '/usr/bin/clang'\ncpp = '/usr/bin/clang++'\nobjc = '/usr/bin/clang'\nar = '/usr/bin/ar'\nstrip = '/usr/bin/strip'\n"
                     "pkg-config = '" + str(tools / 'bin/pkg-config') + "'\n[host_machine]\nsystem = 'darwin'\ncpu_family = 'aarch64'\ncpu = 'arm64'\n"
                     "endian = 'little'\n[properties]\nneeds_exe_wrapper = true\n[built-in options]\nc_args = " + repr(flags) +
                     "\nobjc_args = " + repr(flags) + "\nc_link_args = " + repr(linkflags) + "\nobjc_link_args = " + repr(linkflags) + "\n")
    missing = [o for o in rules['mpv_options']['required'] if o not in MPV_OPTIONS]
    if missing: raise RuntimeError('mpv options break the allow-list: ' + str(missing))
    evidence.mkdir(parents=True, exist_ok=True)
    fingerprint = {'options': MPV_OPTIONS, 'cross': cross.read_text(), 'pc': {p.name: p.read_text() for p in sorted(pc.glob('*.pc'))}}
    # A new meson directory per input set, so a changed recipe never reuses a stale configure (and nothing is deleted).
    build = work / (sdk + '-' + hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()[:12])
    if not (build / 'build.ninja').exists():
        with (evidence / (sdk + '-configure.log')).open('w') as out:
            run([tools / 'bin/meson', 'setup', build, source, '--cross-file', cross] + MPV_OPTIONS, env=env, stdout=out, stderr=subprocess.STDOUT)
    with (evidence / (sdk + '-compile.log')).open('w') as out:
        run([tools / 'bin/ninja', '-C', build, '-j2'], env=env, stdout=out, stderr=subprocess.STDOUT)
    binary = next(build.glob('libAlkemyoMPV.*.dylib'))
    framework = work / (sdk + '-framework') / 'AlkemyoMPV.framework'; framework.mkdir(parents=True, exist_ok=True)
    destination = framework / 'AlkemyoMPV'; shutil.copy2(binary, destination)
    run(['install_name_tool', '-id', '@rpath/AlkemyoMPV.framework/AlkemyoMPV', destination])
    info_plist(framework, 'AlkemyoMPV', rules['frameworks']['AlkemyoMPV']['identifier'], platform, sdk)
    checked = check_binary(destination, 'AlkemyoMPV', required_symbols=['_mpv_create', '_mpv_render_context_create'],
                           forbidden_symbols=['_alkemyo_media_abi', '_alkemyo_media_open', '_alkemyo_subtitle_decode', '_avformat_open_input'])
    receipt = {'schema': 2, 'framework': 'AlkemyoMPV', 'source_commit': MPV_COMMIT, 'source_archive_sha256': MPV_SHA, 'sdk': sdk,
               'target': target, 'options': MPV_OPTIONS, 'builder_sha256': digest(__file__), 'allowlist_sha256': digest(ALLOWLIST),
               'overlay_sha256': {p: digest(ROOT / p) for p in rules['mpv_overlay']}, 'audio_patch_sha256': AUDIO_PATCH_SHA,
               'ffmpeg_sha256': digest(ffmpeg / 'AlkemyoFFmpeg'), 'static_libraries': records, 'binary_sha256': checked['sha256'],
               'load_commands': checked['load_commands'], 'source_compiled': True, 'runtime': 'pending', 'physical_device': 'pending'}
    (evidence / (sdk + '-receipt.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    return framework, receipt


