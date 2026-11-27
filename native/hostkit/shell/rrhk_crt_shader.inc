/* The CRT looks on the graphics card (HOST_KIT D35, stage 2): CRTS (rrhk_crts.inc) drawn into the game's rectangle by our own
 * pass inside SDL's renderer, Direct3D 11 on Windows, OpenGL elsewhere (and on Windows when the player forces it). SDL 2.32
 * leaves the device to the application between SDL_RenderFlush and its next call (SDL_RenderGetD3D11Device, the current GL
 * context): the pass saves every state it sets and puts it back, so SDL's own cache of that state stays true and the menus,
 * notices and chat it draws next are untouched. The picture is uploaded into the pass's own texture (SDL2 cannot hand out the
 * native one), once a frame, instead of the kit's.
 * Not drawn, and the stage-1 look (scanline_sdl.h) shown instead: any other renderer (Direct3D 12 under Variable refresh,
 * SDL's software renderer, OpenGL ES), a CPU rasterizer (Microsoft Basic Render Driver, Mesa llvmpipe / softpipe), Direct3D 11
 * below feature level 10.0, no d3dcompiler_47.dll, or a shader the driver refuses: said once on stderr, never retried in that
 * run. Presentation only: it reads the finished picture; nothing reaches the machine, its state or the netplay digest.
 * Included by rrhk_video.c only; staged beside the shell (retrorecomp/hostkit.py SHELL_INCLUDED). */
#include <stdio.h>
#include "rrhk_crts.inc"

typedef struct RrhkCrtPass {
    int state;                     /* 0 not tried, 1 ready, -1 unavailable for this run */
    const char *backend;           /* "direct3d11" or "opengl" once ready */
    int tex_w, tex_h;              /* the pass's own texture */
    void *device;                  /* the D3D11 device the resources belong to (SDL may make a new one after a device loss) */
#ifdef _WIN32
    struct ID3D11VertexShader *vs;
    struct ID3D11PixelShader *ps[2];          /* flat, curved */
    struct ID3D11Buffer *constants;
    struct ID3D11SamplerState *sampler;
    struct ID3D11RasterizerState *raster;
    struct ID3D11BlendState *blend;
    struct ID3D11Texture2D *texture;
    struct ID3D11ShaderResourceView *view;
#endif
    unsigned program[2], gl_texture;          /* OpenGL */
} RrhkCrtPass;
static RrhkCrtPass crt_pass;

static void crt_unavailable(const char *why) {
    crt_pass.state = -1;
    fprintf(stderr, "[host] CRT look: the graphics card's pass is unavailable (%s): the look is drawn without it\n", why);
}

/* The constants both backends hand the shader (rrhk_crts.inc). lines: the console's lines; curved: the warp. */
static void crt_constants(float out[16], int width, int height, int tex_w, int tex_h, int lines, const SDL_Rect *dst, bool curved) {
    if (lines <= 0 || lines > height * 4) lines = height;
    /* the input grid: the console's lines, and as many columns as the picture has for each line's share of its rows (a game
     * drawn at 2x keeps its 320 columns and 240 lines) */
    const float in_w = (float)width * (float)lines / (float)height, in_h = (float)lines;
    /* no dark gaps above 300 lines a frame nor below two output rows a line, as stage 1 (thin 0.5: the beams sum to one) */
    const bool gaps = lines <= RR_CRT_FINE_LINES && dst->h >= 2 * lines;
    const float values[16] = {
        in_w, in_h, 1.0f / in_w, 1.0f / in_h,
        (float)dst->w, (float)dst->h, 1.0f / (float)dst->w, 1.0f / (float)dst->h,
        (float)width / (float)tex_w, (float)height / (float)tex_h, curved ? 0.031f : 0.0f, curved ? 0.041f : 0.0f,
        gaps ? 0.75f : 0.5f, -2.5f, 0.5f, curved ? 3.0f : 1.0f};
    memcpy(out, values, sizeof values);
}

/* ---------------------------------------------------------------- Direct3D 11 ---------------------------------------------- */
#ifdef _WIN32
#ifndef COBJMACROS
#define COBJMACROS
#endif
#include <d3d11.h>
#include <d3dcompiler.h>

static const GUID crt_iid_dxgi_device = {0x54ec77fa, 0x1377, 0x44e6, {0x8c, 0x32, 0x88, 0xfd, 0x5f, 0x44, 0xc8, 0x4c}};
typedef HRESULT (WINAPI *CrtCompile)(LPCVOID, SIZE_T, LPCSTR, const D3D_SHADER_MACRO *, ID3DInclude *, LPCSTR, LPCSTR, UINT, UINT,
                                     ID3DBlob **, ID3DBlob **);

/* windows.h came in with SDL.h before COBJMACROS: IUnknown's macros are not there, the vtable is */
static void crt_release(void *object) { if (object) ((IUnknown *)object)->lpVtbl->Release((IUnknown *)object); }
static void crt_d3d_release(void) {
#define CRT_RELEASE(p) do { crt_release(p); (p) = NULL; } while (0)
    CRT_RELEASE(crt_pass.vs); CRT_RELEASE(crt_pass.ps[0]); CRT_RELEASE(crt_pass.ps[1]); CRT_RELEASE(crt_pass.constants);
    CRT_RELEASE(crt_pass.sampler); CRT_RELEASE(crt_pass.raster); CRT_RELEASE(crt_pass.blend);
    CRT_RELEASE(crt_pass.view); CRT_RELEASE(crt_pass.texture);
#undef CRT_RELEASE
    crt_pass.tex_w = crt_pass.tex_h = 0;
}

/* A CPU rasterizer behind Direct3D 11 (no graphics driver: VMs, some remote sessions): DXGI's adapter 0x1414:0x8C. */
static bool crt_d3d_software(ID3D11Device *device) {
    IDXGIDevice *dxgi = NULL; IDXGIAdapter *adapter = NULL; DXGI_ADAPTER_DESC desc;
    bool software = false;
    if (SUCCEEDED(ID3D11Device_QueryInterface(device, &crt_iid_dxgi_device, (void **)&dxgi)) &&
        SUCCEEDED(IDXGIDevice_GetAdapter(dxgi, &adapter)) && SUCCEEDED(IDXGIAdapter_GetDesc(adapter, &desc)))
        software = desc.VendorId == 0x1414 && desc.DeviceId == 0x8c;
    if (adapter) IDXGIAdapter_Release(adapter);
    if (dxgi) IDXGIDevice_Release(dxgi);
    return software;
}

static bool crt_d3d_compile(CrtCompile compile, const char *source, size_t size, const char *entry, const char *target,
                            const D3D_SHADER_MACRO *defines, ID3DBlob **code) {
    ID3DBlob *errors = NULL;
    const HRESULT hr = compile(source, size, "rrhk_crts", defines, NULL, entry, target, D3DCOMPILE_OPTIMIZATION_LEVEL3, 0, code, &errors);
    if (FAILED(hr) && errors) fprintf(stderr, "[host] CRT look: %.300s\n", (const char *)ID3D10Blob_GetBufferPointer(errors));
    if (errors) ID3D10Blob_Release(errors);
    return SUCCEEDED(hr);
}

static bool crt_d3d_create(ID3D11Device *device) {
    static HMODULE library;
    /* System32 only: a d3dcompiler_47.dll placed beside a game's executable is never loaded */
#ifndef LOAD_LIBRARY_SEARCH_SYSTEM32
#define LOAD_LIBRARY_SEARCH_SYSTEM32 0x00000800
#endif
    if (!library) library = LoadLibraryExA("d3dcompiler_47.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    CrtCompile compile = library ? (CrtCompile)(void *)GetProcAddress(library, "D3DCompile") : NULL;
    if (!compile) { crt_unavailable("no d3dcompiler_47.dll"); return false; }
    if (ID3D11Device_GetFeatureLevel(device) < D3D_FEATURE_LEVEL_10_0) { crt_unavailable("Direct3D feature level below 10.0"); return false; }
    if (crt_d3d_software(device)) { crt_unavailable("Microsoft Basic Render Driver, no graphics card"); return false; }
    const size_t head = strlen(rrhk_crts_hlsl_head), body = strlen(rrhk_crts_body), tail = strlen(rrhk_crts_hlsl_main);
    char *source = (char *)SDL_malloc(head + body + tail + 1);
    if (!source) { crt_unavailable("no memory"); return false; }
    memcpy(source, rrhk_crts_hlsl_head, head); memcpy(source + head, rrhk_crts_body, body);
    memcpy(source + head + body, rrhk_crts_hlsl_main, tail + 1);
    const D3D_SHADER_MACRO warp[] = {{"RR_WARP", "1"}, {NULL, NULL}};
    ID3DBlob *vs = NULL, *ps[2] = {NULL, NULL};
    bool ok = crt_d3d_compile(compile, source, head + body + tail, "rr_vs", "vs_4_0", NULL, &vs) &&
              crt_d3d_compile(compile, source, head + body + tail, "rr_ps", "ps_4_0", NULL, &ps[0]) &&
              crt_d3d_compile(compile, source, head + body + tail, "rr_ps", "ps_4_0", warp, &ps[1]);
    SDL_free(source);
    if (ok) ok = SUCCEEDED(ID3D11Device_CreateVertexShader(device, ID3D10Blob_GetBufferPointer(vs), ID3D10Blob_GetBufferSize(vs), NULL, &crt_pass.vs));
    for (int i = 0; ok && i < 2; ++i)
        ok = SUCCEEDED(ID3D11Device_CreatePixelShader(device, ID3D10Blob_GetBufferPointer(ps[i]), ID3D10Blob_GetBufferSize(ps[i]), NULL, &crt_pass.ps[i]));
    if (vs) ID3D10Blob_Release(vs);
    for (int i = 0; i < 2; ++i) if (ps[i]) ID3D10Blob_Release(ps[i]);
    D3D11_BUFFER_DESC cb = {64, D3D11_USAGE_DYNAMIC, D3D11_BIND_CONSTANT_BUFFER, D3D11_CPU_ACCESS_WRITE, 0, 0};
    if (ok) ok = SUCCEEDED(ID3D11Device_CreateBuffer(device, &cb, NULL, &crt_pass.constants));
    D3D11_SAMPLER_DESC sd;
    memset(&sd, 0, sizeof sd);
    sd.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
    sd.AddressU = sd.AddressV = sd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
    sd.MaxLOD = D3D11_FLOAT32_MAX;
    if (ok) ok = SUCCEEDED(ID3D11Device_CreateSamplerState(device, &sd, &crt_pass.sampler));
    D3D11_RASTERIZER_DESC rd;
    memset(&rd, 0, sizeof rd);
    rd.FillMode = D3D11_FILL_SOLID; rd.CullMode = D3D11_CULL_NONE; rd.DepthClipEnable = TRUE; rd.ScissorEnable = TRUE;
    if (ok) ok = SUCCEEDED(ID3D11Device_CreateRasterizerState(device, &rd, &crt_pass.raster));
    D3D11_BLEND_DESC bd;
    memset(&bd, 0, sizeof bd);
    bd.RenderTarget[0].SrcBlend = bd.RenderTarget[0].SrcBlendAlpha = D3D11_BLEND_ONE;
    bd.RenderTarget[0].DestBlend = bd.RenderTarget[0].DestBlendAlpha = D3D11_BLEND_ZERO;
    bd.RenderTarget[0].BlendOp = bd.RenderTarget[0].BlendOpAlpha = D3D11_BLEND_OP_ADD;
    bd.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
    if (ok) ok = SUCCEEDED(ID3D11Device_CreateBlendState(device, &bd, &crt_pass.blend));
    if (!ok) { crt_d3d_release(); crt_unavailable("the Direct3D 11 shader was refused"); return false; }
    return true;
}

static bool crt_d3d_upload(ID3D11Device *device, ID3D11DeviceContext *context, const uint32_t *pixels, int width, int height, int pitch) {
    if (!crt_pass.texture || width > crt_pass.tex_w || height > crt_pass.tex_h) {
        if (crt_pass.view) { ID3D11ShaderResourceView_Release(crt_pass.view); crt_pass.view = NULL; }
        if (crt_pass.texture) { ID3D11Texture2D_Release(crt_pass.texture); crt_pass.texture = NULL; }
        const int w = SDL_max(width, crt_pass.tex_w), h = SDL_max(height, crt_pass.tex_h);
        D3D11_TEXTURE2D_DESC td;
        memset(&td, 0, sizeof td);
        td.Width = (UINT)w; td.Height = (UINT)h; td.MipLevels = 1; td.ArraySize = 1;
        td.Format = DXGI_FORMAT_B8G8R8A8_UNORM;                 /* the kit's ARGB8888 in memory order */
        td.SampleDesc.Count = 1; td.Usage = D3D11_USAGE_DEFAULT; td.BindFlags = D3D11_BIND_SHADER_RESOURCE;
        if (FAILED(ID3D11Device_CreateTexture2D(device, &td, NULL, &crt_pass.texture)) ||
            FAILED(ID3D11Device_CreateShaderResourceView(device, (ID3D11Resource *)crt_pass.texture, NULL, &crt_pass.view))) {
            crt_d3d_release();
            return false;
        }
        crt_pass.tex_w = w; crt_pass.tex_h = h;
    }
    const D3D11_BOX box = {0, 0, 0, (UINT)width, (UINT)height, 1};
    ID3D11DeviceContext_UpdateSubresource(context, (ID3D11Resource *)crt_pass.texture, 0, &box, pixels, (UINT)pitch * 4, 0);
    return true;
}

static bool crt_d3d_draw(SDL_Renderer *ren, const uint32_t *pixels, int width, int height, int pitch, const SDL_Rect *dst, int lines, bool curved) {
    ID3D11Device *device = SDL_RenderGetD3D11Device(ren);
    if (!device) { crt_unavailable("no Direct3D 11 device"); return false; }
    if (crt_pass.state == 1 && crt_pass.device != (void *)device) { crt_d3d_release(); crt_pass.state = 0; }   /* a new device */
    if (crt_pass.state == 0) {
        if (!crt_d3d_create(device)) { ID3D11Device_Release(device); return false; }
        crt_pass.state = 1; crt_pass.backend = "direct3d11"; crt_pass.device = device;
        fprintf(stderr, "[host] CRT look: drawn by the graphics card (Direct3D 11, CRTS)\n");
    }
    ID3D11DeviceContext *context = NULL;
    ID3D11Device_GetImmediateContext(device, &context);
    bool drawn = false;
    if (context && crt_d3d_upload(device, context, pixels, width, height, pitch)) {
        float constants[16];
        crt_constants(constants, width, height, crt_pass.tex_w, crt_pass.tex_h, lines, dst, curved);
        D3D11_MAPPED_SUBRESOURCE mapped;
        if (SUCCEEDED(ID3D11DeviceContext_Map(context, (ID3D11Resource *)crt_pass.constants, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped))) {
            memcpy(mapped.pData, constants, sizeof constants);
            ID3D11DeviceContext_Unmap(context, (ID3D11Resource *)crt_pass.constants, 0);
            /* save what the pass sets */
            UINT viewports = D3D11_VIEWPORT_AND_SCISSORRECT_OBJECT_COUNT_PER_PIPELINE, scissors = viewports;
            D3D11_VIEWPORT saved_viewports[D3D11_VIEWPORT_AND_SCISSORRECT_OBJECT_COUNT_PER_PIPELINE];
            D3D11_RECT saved_scissors[D3D11_VIEWPORT_AND_SCISSORRECT_OBJECT_COUNT_PER_PIPELINE];
            ID3D11DeviceContext_RSGetViewports(context, &viewports, saved_viewports);
            ID3D11DeviceContext_RSGetScissorRects(context, &scissors, saved_scissors);
            ID3D11RasterizerState *raster = NULL; ID3D11DeviceContext_RSGetState(context, &raster);
            ID3D11BlendState *blend = NULL; FLOAT factor[4]; UINT sample_mask = 0;
            ID3D11DeviceContext_OMGetBlendState(context, &blend, factor, &sample_mask);
            ID3D11InputLayout *layout = NULL; ID3D11DeviceContext_IAGetInputLayout(context, &layout);
            D3D11_PRIMITIVE_TOPOLOGY topology; ID3D11DeviceContext_IAGetPrimitiveTopology(context, &topology);
            ID3D11VertexShader *vs = NULL; UINT vs_count = 0; ID3D11DeviceContext_VSGetShader(context, &vs, NULL, &vs_count);
            ID3D11PixelShader *ps = NULL; UINT ps_count = 0; ID3D11DeviceContext_PSGetShader(context, &ps, NULL, &ps_count);
            ID3D11Buffer *vs_constants = NULL; ID3D11DeviceContext_VSGetConstantBuffers(context, 0, 1, &vs_constants);
            ID3D11Buffer *ps_constants = NULL; ID3D11DeviceContext_PSGetConstantBuffers(context, 0, 1, &ps_constants);
            ID3D11ShaderResourceView *resource = NULL; ID3D11DeviceContext_PSGetShaderResources(context, 0, 1, &resource);
            ID3D11SamplerState *sampler = NULL; ID3D11DeviceContext_PSGetSamplers(context, 0, 1, &sampler);
            ID3D11RenderTargetView *target = NULL; ID3D11DeviceContext_OMGetRenderTargets(context, 1, &target, NULL);
            if (target) {
                /* draw: the game's rectangle only */
                const D3D11_VIEWPORT viewport = {(FLOAT)dst->x, (FLOAT)dst->y, (FLOAT)dst->w, (FLOAT)dst->h, 0.0f, 1.0f};
                const D3D11_RECT clip = {dst->x, dst->y, dst->x + dst->w, dst->y + dst->h};
                ID3D11DeviceContext_RSSetViewports(context, 1, &viewport);
                ID3D11DeviceContext_RSSetScissorRects(context, 1, &clip);
                ID3D11DeviceContext_RSSetState(context, crt_pass.raster);
                ID3D11DeviceContext_OMSetBlendState(context, crt_pass.blend, NULL, 0xffffffffu);
                ID3D11DeviceContext_IASetInputLayout(context, NULL);
                ID3D11DeviceContext_IASetPrimitiveTopology(context, D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
                ID3D11DeviceContext_VSSetShader(context, crt_pass.vs, NULL, 0);
                ID3D11DeviceContext_PSSetShader(context, crt_pass.ps[curved ? 1 : 0], NULL, 0);
                ID3D11DeviceContext_PSSetConstantBuffers(context, 0, 1, &crt_pass.constants);
                ID3D11DeviceContext_PSSetShaderResources(context, 0, 1, &crt_pass.view);
                ID3D11DeviceContext_PSSetSamplers(context, 0, 1, &crt_pass.sampler);
                ID3D11DeviceContext_Draw(context, 3, 0);
                drawn = true;
            }
            /* put everything back as SDL left it */
            ID3D11DeviceContext_RSSetViewports(context, viewports, saved_viewports);
            ID3D11DeviceContext_RSSetScissorRects(context, scissors, saved_scissors);
            ID3D11DeviceContext_RSSetState(context, raster);
            ID3D11DeviceContext_OMSetBlendState(context, blend, factor, sample_mask);
            ID3D11DeviceContext_IASetInputLayout(context, layout);
            ID3D11DeviceContext_IASetPrimitiveTopology(context, topology);
            ID3D11DeviceContext_VSSetShader(context, vs, NULL, 0);
            ID3D11DeviceContext_PSSetShader(context, ps, NULL, 0);
            ID3D11DeviceContext_VSSetConstantBuffers(context, 0, 1, &vs_constants);
            ID3D11DeviceContext_PSSetConstantBuffers(context, 0, 1, &ps_constants);
            ID3D11DeviceContext_PSSetShaderResources(context, 0, 1, &resource);
            ID3D11DeviceContext_PSSetSamplers(context, 0, 1, &sampler);
            IUnknown *held[] = {(IUnknown *)raster, (IUnknown *)blend, (IUnknown *)layout, (IUnknown *)vs, (IUnknown *)ps,
                                (IUnknown *)vs_constants, (IUnknown *)ps_constants, (IUnknown *)resource, (IUnknown *)sampler,
                                (IUnknown *)target};
            for (size_t i = 0; i < sizeof held / sizeof held[0]; ++i) crt_release(held[i]);
        }
    }
    if (context) ID3D11DeviceContext_Release(context);
    ID3D11Device_Release(device);
    return drawn;
}
#endif

/* ---------------------------------------------------------------- OpenGL --------------------------------------------------- */
#include <SDL_opengl.h>
#ifndef GL_BGRA
#define GL_BGRA 0x80E1
#endif
#ifndef GL_UNSIGNED_INT_8_8_8_8_REV
#define GL_UNSIGNED_INT_8_8_8_8_REV 0x8367
#endif
#ifndef GL_CLAMP_TO_EDGE
#define GL_CLAMP_TO_EDGE 0x812F
#endif
#ifndef GL_FRAGMENT_SHADER
#define GL_FRAGMENT_SHADER 0x8B30
#define GL_VERTEX_SHADER 0x8B31
#define GL_COMPILE_STATUS 0x8B81
#define GL_LINK_STATUS 0x8B82
#define GL_CURRENT_PROGRAM 0x8B8D
#endif
#ifndef GL_ACTIVE_TEXTURE
#define GL_ACTIVE_TEXTURE 0x84E0
#define GL_TEXTURE0 0x84C0
#endif
#ifndef GL_ARRAY_BUFFER
#define GL_ARRAY_BUFFER 0x8892
#define GL_ARRAY_BUFFER_BINDING 0x8894
#endif

typedef struct {
    void (APIENTRY *GetIntegerv)(GLenum, GLint *);
    const GLubyte *(APIENTRY *GetString)(GLenum);
    GLboolean (APIENTRY *IsEnabled)(GLenum);
    void (APIENTRY *Enable)(GLenum);
    void (APIENTRY *Disable)(GLenum);
    void (APIENTRY *Viewport)(GLint, GLint, GLsizei, GLsizei);
    void (APIENTRY *GenTextures)(GLsizei, GLuint *);
    void (APIENTRY *DeleteTextures)(GLsizei, const GLuint *);
    void (APIENTRY *BindTexture)(GLenum, GLuint);
    void (APIENTRY *TexParameteri)(GLenum, GLenum, GLint);
    void (APIENTRY *TexImage2D)(GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void *);
    void (APIENTRY *TexSubImage2D)(GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void *);
    void (APIENTRY *PixelStorei)(GLenum, GLint);
    void (APIENTRY *EnableClientState)(GLenum);
    void (APIENTRY *DisableClientState)(GLenum);
    void (APIENTRY *VertexPointer)(GLint, GLenum, GLsizei, const void *);
    void (APIENTRY *DrawArrays)(GLenum, GLint, GLsizei);
    void (APIENTRY *ActiveTexture)(GLenum);
    void (APIENTRY *BindBuffer)(GLenum, GLuint);
    GLuint (APIENTRY *CreateShader)(GLenum);
    void (APIENTRY *ShaderSource)(GLuint, GLsizei, const char *const *, const GLint *);
    void (APIENTRY *CompileShader)(GLuint);
    void (APIENTRY *GetShaderiv)(GLuint, GLenum, GLint *);
    void (APIENTRY *GetShaderInfoLog)(GLuint, GLsizei, GLsizei *, char *);
    GLuint (APIENTRY *CreateProgram)(void);
    void (APIENTRY *AttachShader)(GLuint, GLuint);
    void (APIENTRY *LinkProgram)(GLuint);
    void (APIENTRY *GetProgramiv)(GLuint, GLenum, GLint *);
    void (APIENTRY *DeleteShader)(GLuint);
    void (APIENTRY *DeleteProgram)(GLuint);
    void (APIENTRY *UseProgram)(GLuint);
    GLint (APIENTRY *GetUniformLocation)(GLuint, const char *);
    void (APIENTRY *Uniform1i)(GLint, GLint);
    void (APIENTRY *Uniform4fv)(GLint, GLsizei, const GLfloat *);
} CrtGl;
static CrtGl gl;

/* The context's version (GL_VERSION begins "major.minor"): the pass needs OpenGL 2.0. Asked before any 2.0 function is looked up,
 * since glXGetProcAddress answers for functions a context does not have. */
static bool crt_gl_version_2(void) {
    const GLubyte *(APIENTRY *get_string)(GLenum) = (const GLubyte *(APIENTRY *)(GLenum))SDL_GL_GetProcAddress("glGetString");
    const char *version = get_string ? (const char *)get_string(GL_VERSION) : NULL;
    int major = 0, minor = 0;
    return version && sscanf(version, "%d.%d", &major, &minor) == 2 && major >= 2;
}

static bool crt_gl_load(void) {
    void **slots = (void **)&gl;
    static const char *const names[] = {"glGetIntegerv", "glGetString", "glIsEnabled", "glEnable", "glDisable", "glViewport",
        "glGenTextures", "glDeleteTextures", "glBindTexture", "glTexParameteri", "glTexImage2D", "glTexSubImage2D", "glPixelStorei",
        "glEnableClientState", "glDisableClientState", "glVertexPointer", "glDrawArrays", "glActiveTexture", "glBindBuffer",
        "glCreateShader", "glShaderSource", "glCompileShader", "glGetShaderiv", "glGetShaderInfoLog", "glCreateProgram",
        "glAttachShader", "glLinkProgram", "glGetProgramiv", "glDeleteShader", "glDeleteProgram", "glUseProgram",
        "glGetUniformLocation", "glUniform1i", "glUniform4fv"};
    for (size_t i = 0; i < sizeof names / sizeof names[0]; ++i)
        if (!(slots[i] = SDL_GL_GetProcAddress(names[i]))) return false;
    return true;
}

static GLuint crt_gl_shader(GLenum kind, const char *const *parts, int count) {
    const GLuint shader = gl.CreateShader(kind);
    gl.ShaderSource(shader, count, parts, NULL);
    gl.CompileShader(shader);
    GLint ok = 0; gl.GetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[400]; gl.GetShaderInfoLog(shader, sizeof log, NULL, log);
        fprintf(stderr, "[host] CRT look: %.300s\n", log);
        gl.DeleteShader(shader);
        return 0;
    }
    return shader;
}

static void crt_gl_release(void) {
    for (int i = 0; i < 2; ++i) if (crt_pass.program[i]) { gl.DeleteProgram(crt_pass.program[i]); crt_pass.program[i] = 0; }
    if (crt_pass.gl_texture) { gl.DeleteTextures(1, &crt_pass.gl_texture); crt_pass.gl_texture = 0; }
    crt_pass.tex_w = crt_pass.tex_h = 0;
}

static bool crt_gl_create(void) {
    if (!crt_gl_version_2()) { crt_unavailable("OpenGL below 2.0"); return false; }
    if (!crt_gl_load()) { crt_unavailable("OpenGL 2.0 functions missing"); return false; }
    const char *renderer = (const char *)gl.GetString(GL_RENDERER);
    if (renderer && (strstr(renderer, "llvmpipe") || strstr(renderer, "softpipe") || strstr(renderer, "Software Rasterizer") ||
                     strstr(renderer, "GDI Generic") || strstr(renderer, "SwiftShader"))) {
        crt_unavailable("a CPU rasterizer, no graphics card"); return false;
    }
    const char *vertex[] = {rrhk_crts_glsl_vertex};
    const GLuint vs = crt_gl_shader(GL_VERTEX_SHADER, vertex, 1);
    bool ok = vs != 0;
    for (int i = 0; ok && i < 2; ++i) {
        const char *fragment[] = {rrhk_crts_glsl_head, i ? "#define RR_WARP 1\n" : "", rrhk_crts_body, rrhk_crts_glsl_main};
        const GLuint fs = crt_gl_shader(GL_FRAGMENT_SHADER, fragment, 4);
        if (!fs) { ok = false; break; }
        const GLuint program = gl.CreateProgram();
        gl.AttachShader(program, vs); gl.AttachShader(program, fs);
        gl.LinkProgram(program);
        gl.DeleteShader(fs);
        GLint linked = 0; gl.GetProgramiv(program, GL_LINK_STATUS, &linked);
        if (!linked) { gl.DeleteProgram(program); ok = false; break; }
        crt_pass.program[i] = program;
    }
    if (vs) gl.DeleteShader(vs);
    if (!ok) { crt_gl_release(); crt_unavailable("the OpenGL shader was refused"); return false; }
    return true;
}

static bool crt_gl_draw(SDL_Renderer *ren, const uint32_t *pixels, int width, int height, int pitch, const SDL_Rect *dst, int lines, bool curved) {
    if (crt_pass.state == 0) {
        if (!crt_gl_create()) return false;
        crt_pass.state = 1; crt_pass.backend = "opengl";
        fprintf(stderr, "[host] CRT look: drawn by the graphics card (OpenGL, CRTS)\n");
    }
    int out_w = 0, out_h = 0;
    SDL_GetRendererOutputSize(ren, &out_w, &out_h);
    /* save what the pass sets */
    GLint program = 0, active = 0, bound = 0, buffer = 0, viewport[4], row_length = 0, alignment = 4;
    gl.GetIntegerv(GL_CURRENT_PROGRAM, &program);
    gl.GetIntegerv(GL_ACTIVE_TEXTURE, &active);
    gl.ActiveTexture(GL_TEXTURE0);
    gl.GetIntegerv(GL_TEXTURE_BINDING_2D, &bound);
    gl.GetIntegerv(GL_ARRAY_BUFFER_BINDING, &buffer);
    gl.GetIntegerv(GL_VIEWPORT, viewport);
    gl.GetIntegerv(GL_UNPACK_ROW_LENGTH, &row_length);
    gl.GetIntegerv(GL_UNPACK_ALIGNMENT, &alignment);
    const GLboolean blend = gl.IsEnabled(GL_BLEND), scissor = gl.IsEnabled(GL_SCISSOR_TEST);
    const GLboolean vertex_array = gl.IsEnabled(GL_VERTEX_ARRAY), color_array = gl.IsEnabled(GL_COLOR_ARRAY);
    const GLboolean coord_array = gl.IsEnabled(GL_TEXTURE_COORD_ARRAY);
    /* the picture into the pass's texture */
    bool ok = true;
    if (!crt_pass.gl_texture || width > crt_pass.tex_w || height > crt_pass.tex_h) {
        if (!crt_pass.gl_texture) gl.GenTextures(1, &crt_pass.gl_texture);
        crt_pass.tex_w = SDL_max(width, crt_pass.tex_w); crt_pass.tex_h = SDL_max(height, crt_pass.tex_h);
        gl.BindTexture(GL_TEXTURE_2D, crt_pass.gl_texture);
        gl.TexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        gl.TexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        gl.TexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        gl.TexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        gl.TexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, crt_pass.tex_w, crt_pass.tex_h, 0, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, NULL);
    }
    gl.BindTexture(GL_TEXTURE_2D, crt_pass.gl_texture);
    gl.PixelStorei(GL_UNPACK_ROW_LENGTH, pitch);
    gl.PixelStorei(GL_UNPACK_ALIGNMENT, 4);
    gl.TexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, height, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, pixels);
    /* draw: one triangle over the game's rectangle (window coordinates are bottom-up) */
    const GLuint chosen = crt_pass.program[curved ? 1 : 0];
    float constants[16];
    crt_constants(constants, width, height, crt_pass.tex_w, crt_pass.tex_h, lines, dst, curved);
    gl.UseProgram(chosen);
    gl.Uniform1i(gl.GetUniformLocation(chosen, "rr_picture"), 0);
    gl.Uniform4fv(gl.GetUniformLocation(chosen, "rr_in"), 1, constants);
    gl.Uniform4fv(gl.GetUniformLocation(chosen, "rr_out"), 1, constants + 4);
    gl.Uniform4fv(gl.GetUniformLocation(chosen, "rr_map"), 1, constants + 8);
    gl.Uniform4fv(gl.GetUniformLocation(chosen, "rr_look"), 1, constants + 12);
    gl.Viewport(dst->x, out_h - dst->y - dst->h, dst->w, dst->h);
    gl.Disable(GL_BLEND); gl.Disable(GL_SCISSOR_TEST);
    if (gl.BindBuffer) gl.BindBuffer(GL_ARRAY_BUFFER, 0);
    static const GLfloat corners[6] = {-1.0f, 1.0f, 3.0f, 1.0f, -1.0f, -3.0f};
    gl.EnableClientState(GL_VERTEX_ARRAY);
    gl.DisableClientState(GL_COLOR_ARRAY); gl.DisableClientState(GL_TEXTURE_COORD_ARRAY);
    gl.VertexPointer(2, GL_FLOAT, 0, corners);
    gl.DrawArrays(GL_TRIANGLES, 0, 3);
    /* put everything back as SDL left it */
    gl.UseProgram((GLuint)program);
    gl.BindTexture(GL_TEXTURE_2D, (GLuint)bound);
    gl.ActiveTexture((GLenum)active);
    if (gl.BindBuffer) gl.BindBuffer(GL_ARRAY_BUFFER, (GLuint)buffer);
    gl.Viewport(viewport[0], viewport[1], viewport[2], viewport[3]);
    gl.PixelStorei(GL_UNPACK_ROW_LENGTH, row_length);
    gl.PixelStorei(GL_UNPACK_ALIGNMENT, alignment);
    if (blend) gl.Enable(GL_BLEND);
    if (scissor) gl.Enable(GL_SCISSOR_TEST);
    if (!vertex_array) gl.DisableClientState(GL_VERTEX_ARRAY);
    if (color_array) gl.EnableClientState(GL_COLOR_ARRAY);
    if (coord_array) gl.EnableClientState(GL_TEXTURE_COORD_ARRAY);
    return ok;
}

/* ---------------------------------------------------------------- the kit's entry ------------------------------------------ */
/* The CRT look drawn by the graphics card into dst, the frame cleared black first. false: not drawn (the stage-1 look then). */
static bool rrhk_crt_pass_draw(SDL_Renderer *ren, const uint32_t *pixels, int width, int height, int pitch, const SDL_Rect *dst,
                               int lines, bool curved) {
    if (crt_pass.state < 0 || !pixels || width <= 0 || height <= 0 || dst->w <= 0 || dst->h <= 0) return false;
    SDL_RendererInfo info;
    if (SDL_GetRendererInfo(ren, &info) != 0 || !info.name) return false;
#ifdef _WIN32
    const bool d3d11 = !strcmp(info.name, "direct3d11");
#else
    const bool d3d11 = false;
#endif
    const bool opengl = !strcmp(info.name, "opengl");
    if (!d3d11 && !opengl) return false;            /* Direct3D 12 (Variable refresh), software, OpenGL ES: stage 1, no message */
    /* the frame black, and the back buffer bound as SDL's target (its Direct3D 11 renderer binds it on a draw, not a clear) */
    SDL_SetRenderDrawColor(ren, 0, 0, 0, 255);
    SDL_RenderClear(ren);
    SDL_RenderFillRect(ren, dst);
    SDL_RenderFlush(ren);
#ifdef _WIN32
    if (d3d11) return crt_d3d_draw(ren, pixels, width, height, pitch, dst, lines, curved);
#endif
    return crt_gl_draw(ren, pixels, width, height, pitch, dst, lines, curved);
}

/* The pass's resources, before the renderer goes (close_run). */
void rrhk_crt_pass_release(void) {
#ifdef _WIN32
    if (crt_pass.backend && !strcmp(crt_pass.backend, "direct3d11")) crt_d3d_release();
#endif
    if (crt_pass.backend && !strcmp(crt_pass.backend, "opengl")) crt_gl_release();
    memset(&crt_pass, 0, sizeof crt_pass);
}
