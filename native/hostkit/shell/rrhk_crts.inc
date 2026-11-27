/* The CRT looks' GPU pass (HOST_KIT D35, stage 2): CRTS, Timothy Lottes' "PUBLIC DOMAIN CRT-STYLED SCALAR" (20180120b, released
 * under the Unlicense; adapted for RetroArch by hunterk in libretro/glsl-shaders `crt/shaders/crt-lottes-fast.glsl`, read at
 * a35069864b4b), ported by Retro-Recomp into one source for HLSL (Direct3D 11, ps_4_0) and GLSL 1.20 (OpenGL): the 8-tap
 * filter, the warp, the four masks and the tone map are CRTS'; the uniforms, the fetch and the entry points are ours.
 * Notice: licenses/crt-lottes.md. Included by rrhk_crt_shader.inc only; staged beside the shell (retrorecomp/hostkit.py). */

/* Inputs, the same names in both languages:
 *   rr_in   = input grid: width, height (console lines), 1/width, 1/height
 *   rr_out  = output rectangle: width, height, 1/width, 1/height
 *   rr_map  = the picture's share of its texture (x, y), warp (x, y)
 *   rr_look = thin (0.5: no gaps), blur (negative), mask dark level, mask kind (1 grille, 3 shadow)
 *   rr_more = the colour ratio's exponent (CRTS' saturation: 1 = none), the mask's cell size in output pixels, the light's
 *             gain after the mask (1 = none; ours), unused
 * The numbers come from the CRT style (scanlines.h rr_crt_styles): soft, sharp, arcade. */
static const char rrhk_crts_hlsl_head[] =
    "cbuffer RrLook : register(b0) { float4 rr_in; float4 rr_out; float4 rr_map; float4 rr_look; float4 rr_more; };\n"
    "Texture2D rr_picture : register(t0);\n"
    "SamplerState rr_sampler : register(s0);\n"
    "#define RR_FETCH(uv) rr_picture.SampleLevel(rr_sampler, (uv) * rr_map.xy, 0).rgb\n";

static const char rrhk_crts_glsl_head[] =
    "#version 120\n"
    "#define float2 vec2\n#define float3 vec3\n#define float4 vec4\n#define frac fract\n"
    "#define saturate(x) clamp((x), 0.0, 1.0)\n"
    "uniform sampler2D rr_picture;\n"
    "uniform vec4 rr_in; uniform vec4 rr_out; uniform vec4 rr_map; uniform vec4 rr_look; uniform vec4 rr_more;\n"
    "varying vec2 rr_uv;\n"
    "#define RR_FETCH(uv) texture2D(rr_picture, (uv) * rr_map.xy).rgb\n";

/* CRTS, in the common subset (float2/float3/float4, frac, saturate, exp2, pow, cos, floor). */
static const char rrhk_crts_body[] =
    "float rr_from_srgb1(float c) { return (c <= 0.04045) ? c * (1.0 / 12.92) : pow(c * (1.0 / 1.055) + (0.055 / 1.055), 2.4); }\n"
    "float3 rr_from_srgb(float3 c) { return float3(rr_from_srgb1(c.r), rr_from_srgb1(c.g), rr_from_srgb1(c.b)); }\n"
    "float rr_to_srgb1(float c) { return (c < 0.0031308) ? c * 12.92 : 1.055 * pow(c, 0.41666) - 0.055; }\n"
    "float3 rr_to_srgb(float3 c) { return float3(rr_to_srgb1(c.r), rr_to_srgb1(c.g), rr_to_srgb1(c.b)); }\n"
    "float3 rr_fetch(float2 uv) { return rr_from_srgb(RR_FETCH(uv)); }\n"
    /* CrtsTone(contrast 1, saturation 0, thin, mask) */
    "float4 rr_tone(float thin, float mask, float kind) {\n"
    "  if (kind == 0.0) mask = 1.0;\n"
    "  if (kind == 1.0) mask = 0.5 + mask * 0.5;\n"
    "  float midOut = 0.18 / ((1.5 - thin) * (0.5 * mask + 0.5));\n"
    "  float pMidIn = 0.18;\n"
    "  return float4(1.0, ((-pMidIn) + midOut) / ((1.0 - pMidIn) * midOut),\n"
    "                ((-pMidIn) * midOut + pMidIn) / (midOut * (-pMidIn) + midOut), 1.0);\n"
    "}\n"
    /* CrtsMask */
    "float3 rr_mask(float2 pos, float dark, float kind) {\n"
    "  float3 m = float3(1.0, 1.0, 1.0);\n"
    "  if (kind == 1.0) {\n"
    "    float x = frac(pos.x * (1.0 / 3.0));\n"
    "    if (x < (1.0 / 3.0)) m.r = dark; else if (x < (2.0 / 3.0)) m.g = dark; else m.b = dark;\n"
    "  } else if (kind == 2.0 || kind == 3.0) {\n"
    "    float period = 3.0;\n"
    "    if (kind == 3.0) { pos.x += pos.y * 2.9999; period = 6.0; }\n"
    "    m = float3(dark, dark, dark);\n"
    "    float x = frac(pos.x / period);\n"
    "    if (x < (1.0 / 3.0)) m.r = 1.0; else if (x < (2.0 / 3.0)) m.g = 1.0; else m.b = 1.0;\n"
    "  }\n"
    "  return m;\n"
    "}\n"
    /* CrtsFilter, 8 taps; ipos in output pixels from the rectangle's top left */
    "float3 rr_crts(float2 ipos) {\n"
    "  float2 inSize = rr_in.xy, rcpIn = rr_in.zw;\n"
    "  float thin = rr_look.x, blur = rr_look.y, mask = rr_look.z, kind = rr_look.w;\n"
    "  float2 pos;\n"
    "#ifdef RR_WARP\n"
    "  pos = ipos * (2.0 * rr_out.zw) - float2(1.0, 1.0);\n"
    "  pos *= float2(1.0 + (pos.y * pos.y) * rr_map.z, 1.0 + (pos.x * pos.x) * rr_map.w);\n"
    "  float vin = (1.0 - ((1.0 - saturate(pos.x * pos.x)) * (1.0 - saturate(pos.y * pos.y)))) * (0.998 + 0.001 * 3.0);\n"
    "  vin = saturate((-vin) * inSize.y + inSize.y);\n"
    "  pos = pos * (0.5 * inSize) + 0.5 * inSize;\n"
    "#else\n"
    "  pos = ipos * (inSize * rr_out.zw);\n"
    "#endif\n"
    "  float y0 = floor(pos.y - 0.5) + 0.5;\n"
    "  float x0 = floor(pos.x - 1.5) + 0.5;\n"
    "  float2 p = float2(x0 * rcpIn.x, y0 * rcpIn.y);\n"
    "  float3 colA0 = rr_fetch(p); p.x += rcpIn.x;\n"
    "  float3 colA1 = rr_fetch(p); p.x += rcpIn.x;\n"
    "  float3 colA2 = rr_fetch(p); p.x += rcpIn.x;\n"
    "  float3 colA3 = rr_fetch(p); p.y += rcpIn.y;\n"
    "  float3 colB3 = rr_fetch(p); p.x -= rcpIn.x;\n"
    "  float3 colB2 = rr_fetch(p); p.x -= rcpIn.x;\n"
    "  float3 colB1 = rr_fetch(p); p.x -= rcpIn.x;\n"
    "  float3 colB0 = rr_fetch(p);\n"
    "  float off = pos.y - y0;\n"
    "  float pi2 = 6.28318530717958;\n"
    "  float scanA = cos(min(0.5, off * thin) * pi2) * 0.5 + 0.5;\n"
    "  float scanB = cos(min(0.5, (-off) * thin + thin) * pi2) * 0.5 + 0.5;\n"
    "  float off0 = pos.x - x0, off1 = off0 - 1.0, off2 = off0 - 2.0, off3 = off0 - 3.0;\n"
    "  float pix0 = exp2(blur * off0 * off0), pix1 = exp2(blur * off1 * off1);\n"
    "  float pix2 = exp2(blur * off2 * off2), pix3 = exp2(blur * off3 * off3);\n"
    "  float pixT = 1.0 / (pix0 + pix1 + pix2 + pix3);\n"
    "#ifdef RR_WARP\n"
    "  pixT *= vin;\n"
    "#endif\n"
    "  scanA *= pixT; scanB *= pixT;\n"
    "  float3 color = (colA0 * pix0 + colA1 * pix1 + colA2 * pix2 + colA3 * pix3) * scanA +\n"
    "                 (colB0 * pix0 + colB1 * pix1 + colB2 * pix2 + colB3 * pix3) * scanB;\n"
    "  color *= rr_mask(floor(ipos / rr_more.y) + float2(0.5, 0.5), mask, kind) * rr_more.z;\n"
    "  float4 tone = rr_tone(thin, mask, kind);\n"
    "  float peak = max(1.0 / (256.0 * 65536.0), max(color.r, max(color.g, color.b)));\n"
    "  float3 ratio = color * (1.0 / peak);\n"
    "  ratio = pow(ratio, float3(rr_more.x, rr_more.x, rr_more.x));\n"   /* CRTS_SATURATION, contrast 1 */
    "  peak = peak * (1.0 / (peak * tone.y + tone.z));\n"
    "  return rr_to_srgb(ratio * peak);\n"
    "}\n";

/* Entry points: a full-rectangle triangle; uv runs 0..1 over the rectangle from its top left. */
static const char rrhk_crts_hlsl_main[] =
    "struct RrV { float4 pos : SV_Position; float2 uv : TEXCOORD0; };\n"
    "RrV rr_vs(uint id : SV_VertexID) {\n"
    "  RrV v; float2 t = float2((id << 1) & 2, id & 2);\n"
    "  v.uv = t; v.pos = float4(t * float2(2.0, -2.0) + float2(-1.0, 1.0), 0.0, 1.0); return v;\n"
    "}\n"
    "float4 rr_ps(RrV v) : SV_Target { return float4(rr_crts(v.uv * rr_out.xy), 1.0); }\n";

static const char rrhk_crts_glsl_vertex[] =
    "#version 120\n"
    "varying vec2 rr_uv;\n"
    "void main() { rr_uv = vec2(gl_Vertex.x * 0.5 + 0.5, 0.5 - gl_Vertex.y * 0.5); gl_Position = vec4(gl_Vertex.xy, 0.0, 1.0); }\n";

static const char rrhk_crts_glsl_main[] =
    "void main() { gl_FragColor = vec4(rr_crts(rr_uv * rr_out.xy), 1.0); }\n";
