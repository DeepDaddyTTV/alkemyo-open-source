#ifndef ALKEMYO_NATIVE_BUFFER_H
#define ALKEMYO_NATIVE_BUFFER_H
#include <stdint.h>
// Private, versioned libmpv render extension. Never passed to an unpatched backend.
#define ALKEMYO_NATIVE_BUFFER_API "alkemyo-cvpixelbuffer-v1"
#define ALKEMYO_NATIVE_BUFFER_PARAM 10001
// ABI 2 (tvHdrPolicy.output) adds the subtitle plane; a backend that knows only ABI 1 rejects it and the caller retries with 1.
#define ALKEMYO_NATIVE_BUFFER_ABI 2
#define ALKEMYO_NATIVE_BUFFER_ABI_MIN 1
struct alkemyo_native_frame {
    uint32_t abi;
    uint32_t flags; // bit 0: direct VideoToolbox buffer; bit 1: SDR compositor; bit 2: HDR (PQ/HLG) direct buffer
    void *pixel_buffer; // retained CVPixelBufferRef; consumer must release once
    double pts;
    double duration;
    uint64_t generation; // incremented on VO reset (seek/discontinuity)
    int width, height;
    // ABI 2: subtitles beside an HDR direct buffer, which is never composited (that would relabel HDR code values).
    void *subtitle_buffer; // retained BGRA premultiplied CVPixelBufferRef at the render size when the subtitles changed, else NULL
    uint64_t subtitle_generation; // changes whenever the subtitle image changes; an empty change with no buffer clears it
};
#endif
