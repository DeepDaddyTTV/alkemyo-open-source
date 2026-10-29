// Alkemyo native sample-buffer render backend for mpv v0.41.0.
// LGPL-2.1-or-later, matching the upstream render backend integration.
#include <CoreVideo/CoreVideo.h>
#include <math.h>
#include <libavutil/hwcontext.h>
#include <libavutil/frame.h>
#include "libmpv.h"
#include "alkemyo_native_buffer.h"
#include "sub/osd.h"
#include "sub/draw_bmp.h"
#include "video/hwdec.h"
#include "video/mp_image.h"
#include "video/img_format.h"

struct priv {
    struct render_backend sw;
    struct mp_hwdec_ctx hw;
    struct mp_image_params source, software_source;
    struct mp_rect src, dst;
    struct mp_osd_res osd_size;
    struct osd_state *osd;
    CVPixelBufferPoolRef pool;
    int width, height;
    uint64_t generation;
    // ABI 2 subtitle plane (tvHdrPolicy.output): the overlay renderer and the last subtitle change it delivered.
    struct mp_draw_sub_cache *subtitles;
    int64_t subtitle_change; bool subtitle_shown;
    uint64_t subtitle_generation;
};
static int init(struct render_backend *ctx, mpv_render_param *params)
{
    char *api = get_mpv_render_param(params, MPV_RENDER_PARAM_API_TYPE, NULL);
    if (!api || strcmp(api, ALKEMYO_NATIVE_BUFFER_API)) return MPV_ERROR_NOT_IMPLEMENTED;
    struct priv *p = ctx->priv = talloc_zero(NULL, struct priv);
    p->sw = (struct render_backend){.global=ctx->global,.log=ctx->log,.fns=&render_backend_sw};
    mpv_render_param software[]={{MPV_RENDER_PARAM_API_TYPE,MPV_RENDER_API_TYPE_SW},{0,NULL}};
    int error=p->sw.fns->init(&p->sw,software);
    if (error<0) return error;
    ctx->hwdec_devs=hwdec_devices_create();
    p->hw.driver_name="alkemyo-videotoolbox";
    p->hw.hw_imgfmt=IMGFMT_VIDEOTOOLBOX;
    if (av_hwdevice_ctx_create(&p->hw.av_device_ref,AV_HWDEVICE_TYPE_VIDEOTOOLBOX,NULL,NULL,0)>=0)
        hwdec_devices_add(ctx->hwdec_devs,&p->hw);
    p->generation=1;
    p->subtitles=mp_draw_sub_alloc(p,ctx->global);p->subtitle_change=-1;
    return 0;
}
static bool check_format(struct render_backend *ctx,int format)
{
    struct priv *p=ctx->priv;
    return format==IMGFMT_VIDEOTOOLBOX || p->sw.fns->check_format(&p->sw,format);
}
static void reconfig(struct render_backend *ctx,struct mp_image_params *params)
{
    struct priv *p=ctx->priv;p->source=*params;
}
static void reset(struct render_backend *ctx)
{
    struct priv *p=ctx->priv;p->generation++;
    p->subtitle_change=-1; // resend the subtitle plane after a seek or discontinuity
    p->sw.fns->reset(&p->sw);
}
static void update_external(struct render_backend *ctx,struct vo *vo)
{
    struct priv *p=ctx->priv;p->osd=vo ? vo->osd:NULL;
    p->sw.fns->update_external(&p->sw,vo);
}
static void resize(struct render_backend *ctx,struct mp_rect *src,struct mp_rect *dst,struct mp_osd_res *osd)
{
    struct priv *p=ctx->priv;p->src=*src;p->dst=*dst;p->osd_size=*osd;
    p->sw.fns->resize(&p->sw,src,dst,osd);
}
static int get_target_size(struct render_backend *ctx,mpv_render_param *params,int *w,int *h)
{
    int *size=get_mpv_render_param(params,MPV_RENDER_PARAM_SW_SIZE,NULL);
    // A pixel budget, not an implicit resize: reject oversized requested surfaces.
    if (!size || size[0]<=0 || size[1]<=0 || (uint64_t)size[0]*size[1]>16777216) return MPV_ERROR_INVALID_PARAMETER;
    *w=size[0];*h=size[1];return 0;
}
// HDR10/HLG (tvHdrPolicy.output): the decoder buffer keeps its own tags; mpv's parsed tags and SMPTE ST 2086 / CTA-861.3
// metadata are added only where the decoder left them out, so AVFoundation and the TV get the stream's real HDR description.
static void put16(uint8_t *at,double value,double unit){uint32_t v=(uint32_t)fmax(0,fmin(65535,lround(value/unit)));at[0]=v>>8;at[1]=v;}
static void put32(uint8_t *at,double value,double unit){uint32_t v=(uint32_t)fmax(0,fmin(4294967295.0,llround(value/unit)));at[0]=v>>24;at[1]=v>>16;at[2]=v>>8;at[3]=v;}
static void attach_missing(CVPixelBufferRef pixel,CFStringRef key,CFTypeRef value)
{
    if (!value) return;
    CFTypeRef present=CVBufferCopyAttachment(pixel,key,NULL);
    if (present) {CFRelease(present);return;}
    CVBufferSetAttachment(pixel,key,value,kCVAttachmentMode_ShouldPropagate);
}
static bool tag_hdr(CVPixelBufferRef pixel,const struct mp_image_params *params)
{
    enum pl_color_transfer trc=params->color.transfer;
    if (trc!=PL_COLOR_TRC_PQ && trc!=PL_COLOR_TRC_HLG) return false;
    attach_missing(pixel,kCVImageBufferColorPrimariesKey,params->color.primaries==PL_COLOR_PRIM_BT_2020 ? kCVImageBufferColorPrimaries_ITU_R_2020:NULL);
    attach_missing(pixel,kCVImageBufferTransferFunctionKey,trc==PL_COLOR_TRC_PQ ? kCVImageBufferTransferFunction_SMPTE_ST_2084_PQ:kCVImageBufferTransferFunction_ITU_R_2100_HLG);
    attach_missing(pixel,kCVImageBufferYCbCrMatrixKey,params->repr.sys==PL_COLOR_SYSTEM_BT_2020_NC ? kCVImageBufferYCbCrMatrix_ITU_R_2020:NULL);
    const struct pl_hdr_metadata *hdr=&params->color.hdr;
    if (trc==PL_COLOR_TRC_PQ && hdr->max_luma>0 && hdr->prim.red.x>0) {
        // ST 2086 order: green, blue, red, white point (0.00002 units), then max and min luminance (0.0001 cd/m2).
        uint8_t data[24];
        put16(data+0,hdr->prim.green.x,0.00002);put16(data+2,hdr->prim.green.y,0.00002);
        put16(data+4,hdr->prim.blue.x,0.00002);put16(data+6,hdr->prim.blue.y,0.00002);
        put16(data+8,hdr->prim.red.x,0.00002);put16(data+10,hdr->prim.red.y,0.00002);
        put16(data+12,hdr->prim.white.x,0.00002);put16(data+14,hdr->prim.white.y,0.00002);
        put32(data+16,hdr->max_luma,0.0001);put32(data+20,hdr->min_luma,0.0001);
        CFDataRef value=CFDataCreate(NULL,data,sizeof(data));
        attach_missing(pixel,kCVImageBufferMasteringDisplayColorVolumeKey,value);
        if (value) CFRelease(value);
    }
    if (trc==PL_COLOR_TRC_PQ && (hdr->max_cll>0 || hdr->max_fall>0)) {
        uint8_t data[4];put16(data,hdr->max_cll,1);put16(data+2,hdr->max_fall,1);
        CFDataRef value=CFDataCreate(NULL,data,sizeof(data));
        attach_missing(pixel,kCVImageBufferContentLightLevelInfoKey,value);
        if (value) CFRelease(value);
    }
    return true;
}
// The subtitle plane for an HDR direct buffer: a BGRA premultiplied image at the render size, sent only when it changed.
static void subtitle_plane(struct priv *p,double pts,struct alkemyo_native_frame *out)
{
    out->subtitle_generation=p->subtitle_generation;
    if (!p->osd || !p->subtitles) return;
    struct sub_bitmap_list *list=osd_render(p->osd,p->osd_size,pts,0,mp_draw_sub_formats);
    if (!list) return;
    bool shown=list->num_items>0;
    if (list->change_id==p->subtitle_change && shown==p->subtitle_shown) {talloc_free(list);return;}
    p->subtitle_change=list->change_id;p->subtitle_shown=shown;p->subtitle_generation++;
    out->subtitle_generation=p->subtitle_generation;
    if (!shown) {talloc_free(list);return;}
    int act=0,mod=0;struct mp_rect act_rc[1],mod_rc[1];
    struct mp_image *overlay=mp_draw_sub_overlay(p->subtitles,list,act_rc,0,&act,mod_rc,0,&mod);
    if (overlay && overlay->w>0 && overlay->h>0) {
        CVPixelBufferRef pixel=NULL;
        const void *keys[]={kCVPixelBufferIOSurfacePropertiesKey};CFDictionaryRef empty=CFDictionaryCreate(NULL,NULL,NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
        const void *values[]={empty};CFDictionaryRef attributes=CFDictionaryCreate(NULL,keys,values,1,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
        if (CVPixelBufferCreate(NULL,overlay->w,overlay->h,kCVPixelFormatType_32BGRA,attributes,&pixel)==kCVReturnSuccess) {
            CVPixelBufferLockBaseAddress(pixel,0);
            uint8_t *dst=CVPixelBufferGetBaseAddress(pixel);size_t stride=CVPixelBufferGetBytesPerRow(pixel);
            for (int y=0;y<overlay->h;y++) memcpy(dst+y*stride,overlay->planes[0]+y*overlay->stride[0],(size_t)overlay->w*4);
            CVPixelBufferUnlockBaseAddress(pixel,0);
            out->subtitle_buffer=(void *)pixel;
        }
        CFRelease(attributes);CFRelease(empty);
    }
    talloc_free(list);
}
static bool overlays(struct priv *p,double pts)
{
    if (!p->osd) return false;
    bool formats[SUBBITMAP_COUNT]={[SUBBITMAP_LIBASS]=true,[SUBBITMAP_BGRA]=true};
    struct sub_bitmap_list *list=osd_render(p->osd,p->osd_size,pts,0,formats);
    bool present=list && list->num_items>0;
    talloc_free(list);return present;
}
static bool make_pool(struct priv *p,int width,int height)
{
    if (p->pool && p->width==width && p->height==height) return true;
    if (p->pool) CVPixelBufferPoolRelease(p->pool);
    p->pool=NULL;p->width=width;p->height=height;
    int format=kCVPixelFormatType_32BGRA,alignment=64;
    CFNumberRef values[]={CFNumberCreate(NULL,kCFNumberIntType,&width),CFNumberCreate(NULL,kCFNumberIntType,&height),CFNumberCreate(NULL,kCFNumberIntType,&format),CFNumberCreate(NULL,kCFNumberIntType,&alignment)};
    CFDictionaryRef surface=CFDictionaryCreate(NULL,NULL,NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    const void *keys[]={kCVPixelBufferWidthKey,kCVPixelBufferHeightKey,kCVPixelBufferPixelFormatTypeKey,kCVPixelBufferBytesPerRowAlignmentKey,kCVPixelBufferIOSurfacePropertiesKey};
    const void *attributes_values[]={values[0],values[1],values[2],values[3],surface};
    CFDictionaryRef attributes=CFDictionaryCreate(NULL,keys,attributes_values,5,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    CFRelease(surface);
    CVReturn result=CVPixelBufferPoolCreate(NULL,NULL,attributes,&p->pool);
    CFRelease(attributes);for(int i=0;i<4;i++) CFRelease(values[i]);
    return result==kCVReturnSuccess;
}
static int render(struct render_backend *ctx,mpv_render_param *params,struct vo_frame *frame)
{
    struct priv *p=ctx->priv;
    struct alkemyo_native_frame *out=get_mpv_render_param(params,ALKEMYO_NATIVE_BUFFER_PARAM,NULL);
    int *size=get_mpv_render_param(params,MPV_RENDER_PARAM_SW_SIZE,NULL);
    if (!out || out->abi<ALKEMYO_NATIVE_BUFFER_ABI_MIN || out->abi>ALKEMYO_NATIVE_BUFFER_ABI || out->pixel_buffer || !size) return MPV_ERROR_INVALID_PARAMETER;
    struct mp_image *image=frame->current;
    if (!image || (!isfinite(image->pts) || image->pts == MP_NOPTS_VALUE)) return 0;
    out->pts=image->pts;out->duration=frame->approx_duration;out->generation=p->generation;
    // Preserve the decoder-owned buffer and its color/HDR attachments. It is immutable.
    bool natural_aspect=abs(mp_rect_w(p->dst)*image->h-mp_rect_h(p->dst)*image->w)<image->w+image->h;
    bool full=p->src.x0==0 && p->src.y0==0 && p->src.x1==image->w && p->src.y1==image->h;
    // ABI 2: an HDR (PQ/HLG) direct buffer stays direct with subtitles on, which come beside it as their own plane.
    // Dolby Vision profile 5 is IPT, not BT.2020 YCbCr, so it is never handed over as a direct buffer.
    bool hdr=pl_color_space_is_hdr(&image->params.color) && image->params.repr.sys!=PL_COLOR_SYSTEM_DOLBYVISION;
    bool plane=out->abi>=2 && hdr;
    if (image->imgfmt==IMGFMT_VIDEOTOOLBOX && !image->params.rotate && !image->params.vflip && full && natural_aspect && image->params.repr.sys!=PL_COLOR_SYSTEM_DOLBYVISION && (plane || !overlays(p,image->pts))) {
        CVPixelBufferRef pixel=(CVPixelBufferRef)image->planes[3];
        if (pixel) {
            bool tagged=hdr && tag_hdr(pixel,&image->params);
            out->pixel_buffer=(void *)CVPixelBufferRetain(pixel);out->flags=1|(tagged ? 4:0);
            out->width=(int)CVPixelBufferGetWidth(pixel);out->height=(int)CVPixelBufferGetHeight(pixel);
            if (plane) subtitle_plane(p,image->pts,out);
            return 0;
        }
    }
    // mpv's existing software color conversion and ASS/bitmap compositor is the
    // fallback for software codecs and overlays. This path is explicitly SDR.
    // Never relabel HDR code values as sRGB when a native passthrough is unavailable.
    if (pl_color_space_is_hdr(&image->params.color)) return MPV_ERROR_UNSUPPORTED;
    struct mp_image *download=NULL;
    if (image->imgfmt==IMGFMT_VIDEOTOOLBOX) {
        AVFrame *input=mp_image_to_av_frame(image),*cpu=av_frame_alloc();
        if (!input || !cpu || av_hwframe_transfer_data(cpu,input,0)<0) {av_frame_free(&input);av_frame_free(&cpu);return MPV_ERROR_UNSUPPORTED;}
        av_frame_copy_props(cpu,input);download=mp_image_from_av_frame(cpu);
        av_frame_free(&input);av_frame_free(&cpu);
        if (!download) return MPV_ERROR_NOMEM;
        image=download;
    }
    if (!make_pool(p,size[0],size[1])) {talloc_free(download);return MPV_ERROR_NOMEM;}
    int limit=3;CFNumberRef number=CFNumberCreate(NULL,kCFNumberIntType,&limit);
    const void *key=kCVPixelBufferPoolAllocationThresholdKey;
    CFDictionaryRef aux=CFDictionaryCreate(NULL,&key,(const void **)&number,1,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    CVPixelBufferRef pixel=NULL;CVReturn result=CVPixelBufferPoolCreatePixelBufferWithAuxAttributes(NULL,p->pool,aux,&pixel);
    CFRelease(aux);CFRelease(number);
    if (result==kCVReturnWouldExceedAllocationThreshold) {talloc_free(download);return 0;}
    if (result!=kCVReturnSuccess) {talloc_free(download);return MPV_ERROR_NOMEM;}
    CVPixelBufferLockBaseAddress(pixel,0);
    size_t stride=CVPixelBufferGetBytesPerRow(pixel);void *data=CVPixelBufferGetBaseAddress(pixel);
    mpv_render_param software[]={{MPV_RENDER_PARAM_SW_SIZE,size},{MPV_RENDER_PARAM_SW_FORMAT,"bgr0"},{MPV_RENDER_PARAM_SW_STRIDE,&stride},{MPV_RENDER_PARAM_SW_POINTER,data},{0,NULL}};
    if (!mp_image_params_equal(&p->software_source,&image->params)) {
        p->software_source=image->params;p->sw.fns->reconfig(&p->sw,&image->params);
    }
    struct vo_frame copy=*frame;copy.current=image;
    int error=p->sw.fns->render(&p->sw,software,&copy);
    if (error>=0) for(int y=0;y<size[1];y++) for(int x=0;x<size[0];x++) ((uint8_t *)data)[y*stride+x*4+3]=255;
    CVPixelBufferUnlockBaseAddress(pixel,0);talloc_free(download);
    if (error<0) {CVPixelBufferRelease(pixel);return error;}
    CVBufferSetAttachment(pixel,kCVImageBufferColorPrimariesKey,kCVImageBufferColorPrimaries_ITU_R_709_2,kCVAttachmentMode_ShouldPropagate);
    CVBufferSetAttachment(pixel,kCVImageBufferTransferFunctionKey,kCVImageBufferTransferFunction_sRGB,kCVAttachmentMode_ShouldPropagate);
    out->pixel_buffer=(void *)pixel;out->flags=2;out->width=size[0];out->height=size[1];return 0;
}
static void destroy(struct render_backend *ctx)
{
    struct priv *p=ctx->priv;if (!p) return;
    if (ctx->hwdec_devs) {hwdec_devices_remove(ctx->hwdec_devs,&p->hw);hwdec_devices_destroy(ctx->hwdec_devs);ctx->hwdec_devs=NULL;}
    av_buffer_unref(&p->hw.av_device_ref);
    if (p->pool) CVPixelBufferPoolRelease(p->pool);
    if(p->sw.priv) {p->sw.fns->destroy(&p->sw);talloc_free(p->sw.priv);}
    talloc_free(p);ctx->priv=NULL;
}
const struct render_backend_fns render_backend_alkemyo={.init=init,.check_format=check_format,.reconfig=reconfig,.reset=reset,.update_external=update_external,.resize=resize,.get_target_size=get_target_size,.render=render,.destroy=destroy};
