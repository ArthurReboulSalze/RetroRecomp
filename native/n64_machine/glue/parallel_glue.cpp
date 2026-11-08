/* Retro-Recomp Nintendo 64: ParaLLEl-RDP behind the Mupen64Plus graphics-plugin interface and the libretro Vulkan interface.
 * Copyright (c) 2026 Retro-Recomp contributors. SPDX-License-Identifier: MIT
 *
 * Written from the interfaces only: the plugin entry points of the core's m64p_plugin.h (GFX_INFO), the libretro Vulkan
 * interface (libretro_vulkan.h), the public parallel-rdp API (rdp_device.hpp, video_interface.hpp, MIT) and its MIT
 * integration example, and the RDP command lengths of the hardware documentation. It replaces unmarked glue files. */
#include "parallel.h"
#include <memory>
#include <vector>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include "context.hpp"
#include "device.hpp"
#include "rdp_device.hpp"
#include "video_interface.hpp"

extern "C" {
extern bool libretro_swap_buffer;   // libretro.c hands a frame to the frontend only when the video plugin sets it
#include "m64p_types.h"
#include "m64p_plugin.h"
}

namespace {
const retro_hw_render_interface_vulkan *g_vk;
std::unique_ptr<Vulkan::Context> g_context;
std::unique_ptr<Vulkan::Device> g_device;
std::unique_ptr<RDP::CommandProcessor> g_rdp;
GFX_INFO g_gfx;
bool g_have_gfx;

// Options (the core passes them before parallel_init; changing upscaling needs a new context, as in every frontend)
bool o_sync = true, o_ss_read_back = false, o_ss_dither = true, o_divot = true, o_gamma = true, o_vi_aa = true;
bool o_vi_scale = true, o_dither = true, o_weave = false, o_native_lod = false, o_native_texrect = true;
unsigned o_upscale = 1, o_downscale = 0, o_overscan = 0;
bool g_threaded_commands = false;               // parallel-rdp's command worker thread (play only: not deterministic)

std::vector<Vulkan::ImageHandle> g_held;        // one presented image per frontend sync index
std::vector<retro_vulkan_image> g_images;
bool g_valid = false;
unsigned g_width = 0, g_height = 0;
std::vector<uint32_t> g_words;                  // RDP command words not yet complete

// Length of each RDP command in 64-bit words, by its 6-bit opcode (hardware documentation): a triangle is 4 words of edge
// coefficients, plus 8 for shade, plus 8 for texture, plus 2 for depth.
unsigned command_length(uint32_t op)
{
	switch (op) {
	case 0x08: return 4;  case 0x09: return 6;  case 0x0a: return 12; case 0x0b: return 14;   // fill / textured
	case 0x0c: return 12; case 0x0d: return 14; case 0x0e: return 20; case 0x0f: return 22;   // shaded variants
	case 0x24: case 0x25: return 2;                                                          // texture rectangles
	default: return 1;
	}
}

constexpr uint32_t MI_INTR_DP = 0x20;
constexpr uint32_t DPC_STATUS_XBUS_DMEM = 0x1;
constexpr uint32_t RDP_SYNC_FULL = 0x29;
}

extern "C" {

const VkApplicationInfo *parallel_get_application_info(void)
{
	static const VkApplicationInfo info = {VK_STRUCTURE_TYPE_APPLICATION_INFO, nullptr, "Retro-Recomp N64", 0,
	                                       "parallel-rdp", 0, VK_API_VERSION_1_1};
	return &info;
}

bool parallel_create_device(struct retro_vulkan_context *out, VkInstance instance, VkPhysicalDevice gpu, VkSurfaceKHR surface,
                            PFN_vkGetInstanceProcAddr gipa, const char **exts, unsigned num_exts, const char **, unsigned,
                            const VkPhysicalDeviceFeatures *features)
{
	if (!Vulkan::Context::init_loader(gipa))
		return false;
	g_context.reset(new Vulkan::Context);
	Vulkan::Context::SystemHandles handles = {};
	g_context->set_system_handles(handles);
	static const VkPhysicalDeviceFeatures none = {};
	if (!g_context->init_device_from_instance(instance, gpu, surface, exts, num_exts, features ? features : &none,
	                                          Vulkan::CONTEXT_CREATION_DISABLE_BINDLESS_BIT)) {
		g_context.reset();
		return false;
	}
	const auto &q = g_context->get_queue_info();
	out->gpu = g_context->get_gpu();
	out->device = g_context->get_device();
	out->queue = q.queues[Vulkan::QUEUE_INDEX_GRAPHICS];
	out->queue_family_index = q.family_indices[Vulkan::QUEUE_INDEX_GRAPHICS];
	out->presentation_queue = out->queue;
	out->presentation_queue_family_index = out->queue_family_index;
	g_context->release_device();   // the frontend owns the VkDevice
	return true;
}

void parallel_set_vulkan_interface(const struct retro_hw_render_interface_vulkan *vulkan) { g_vk = vulkan; }
void parallel_set_threaded_commands(bool enable) { g_threaded_commands = enable; }

bool parallel_init(void)
{
	if (!g_context || !g_vk || !g_have_gfx)
		return false;
	uint32_t mask = g_vk->get_sync_index_mask(g_vk->handle), frames = 0;
	for (unsigned i = 0; i < 32; i++)
		if (mask & (1u << i)) frames = i + 1;
	if (!frames) frames = 1;

	g_held.clear(); g_images.clear(); g_rdp.reset(); g_device.reset();   // a context reset re-initialises from scratch
	g_device.reset(new Vulkan::Device);
	g_device->set_context(*g_context);
	g_device->init_frame_contexts(frames);
	g_device->set_queue_lock([]() { g_vk->lock_queue(g_vk->handle); }, []() { g_vk->unlock_queue(g_vk->handle); });

	const auto &features = g_device->get_device_features();
	if (!features.supports_external_memory_host) {
		fprintf(stderr, "n64 glue: the Vulkan device cannot import host memory (VK_EXT_external_memory_host)\n");
		return false;
	}
	size_t rdram_size = (g_gfx.version >= 2 && g_gfx.RDRAM_SIZE) ? *g_gfx.RDRAM_SIZE : 8u * 1024 * 1024;
	uintptr_t ptr = reinterpret_cast<uintptr_t>(g_gfx.RDRAM);
	size_t align = features.host_memory_properties.minImportedHostPointerAlignment;
	size_t offset = align ? (ptr & (align - 1)) : 0;

	RDP::CommandProcessorFlags flags = 0;
	if (o_upscale == 2) flags |= RDP::COMMAND_PROCESSOR_FLAG_UPSCALING_2X_BIT;
	else if (o_upscale == 4) flags |= RDP::COMMAND_PROCESSOR_FLAG_UPSCALING_4X_BIT;
	else if (o_upscale == 8) flags |= RDP::COMMAND_PROCESSOR_FLAG_UPSCALING_8X_BIT;
	if (o_upscale > 1 && o_ss_read_back) flags |= RDP::COMMAND_PROCESSOR_FLAG_SUPER_SAMPLED_READ_BACK_BIT;
	if (o_upscale > 1 && o_ss_dither) flags |= RDP::COMMAND_PROCESSOR_FLAG_SUPER_SAMPLED_DITHER_BIT;

	// Record RDP commands on the emulation thread: with parallel-rdp's own worker thread the GPU reads RDRAM at times that vary
	// from run to run, and two identical runs end with different framebuffer pixels (measured: 36 to 500 frames of 1,500).
	// Deterministic output is what the native-versus-reference proof needs. parallel_set_threaded_commands(true) restores the
	// worker (a faster, non-deterministic option of play).
	if (!g_threaded_commands) {
#ifdef _WIN32
		_putenv("PARALLEL_RDP_SINGLE_THREADED_COMMAND=1");
#else
		setenv("PARALLEL_RDP_SINGLE_THREADED_COMMAND", "1", 0);
#endif
	}
	// The hidden RDRAM holds one byte per 16-bit word (parallel-rdp's shaders/memory_interfacing.h): half the size of RDRAM. A smaller
	// buffer loses the coverage of framebuffers higher in memory, and the VI's filters then eat thin text.
	g_rdp.reset(new RDP::CommandProcessor(*g_device, reinterpret_cast<void *>(ptr - offset), offset, rdram_size,
	                                      rdram_size / 2, flags));
	if (!g_rdp->device_is_supported()) {
		fprintf(stderr, "n64 glue: the Vulkan device lacks what parallel-rdp needs\n");
		g_rdp.reset();
		return false;
	}
	RDP::Quirks quirks;
	quirks.set_native_texture_lod(o_native_lod);
	quirks.set_native_resolution_tex_rect(o_native_texrect);
	g_rdp->set_quirks(quirks);
	g_held.assign(frames, Vulkan::ImageHandle{});
	g_images.assign(frames, retro_vulkan_image{});
	g_words.clear();
	return true;
}

void parallel_deinit(void)
{
	g_held.clear();
	g_images.clear();
	g_rdp.reset();
	g_device.reset();
	g_context.reset();
	g_valid = false;
}

bool parallel_frame_is_valid(void) { return g_valid; }
unsigned parallel_frame_width(void) { return g_width; }
unsigned parallel_frame_height(void) { return g_height; }

void parallel_get_geometry(struct retro_game_geometry *geometry)
{
	geometry->base_width = 640 * o_upscale >> o_downscale;
	geometry->base_height = 480 * o_upscale >> o_downscale;
	geometry->max_width = 640 * 8;
	geometry->max_height = 480 * 8;
	geometry->aspect_ratio = 4.0f / 3.0f;
}

/* Gate only: wait until the GPU has finished every RDP command handed over so far, so that a hash of RDRAM taken between
   frames does not race with framebuffer writes still in flight (the game itself only reads them after a full sync). */
void parallel_quiesce(void)
{
	if (g_rdp)
		g_rdp->wait_for_timeline(g_rdp->signal_timeline());
}

void parallel_profile_video_refresh_begin(void) {}
void parallel_profile_video_refresh_end(void) {}

void parallel_set_synchronous_rdp(bool e) { o_sync = e; }
void parallel_set_upscaling(unsigned f, bool ss) { o_upscale = (f == 2 || f == 4 || f == 8) ? f : 1; o_ss_read_back = ss; }
void parallel_set_super_sampled_read_back_dither(bool e) { o_ss_dither = e; }
void parallel_set_downscaling_steps(unsigned s) { o_downscale = s; }
void parallel_set_overscan_crop(unsigned p) { o_overscan = p; }
void parallel_set_divot_filter(bool e) { o_divot = e; }
void parallel_set_gamma_dither(bool e) { o_gamma = e; }
void parallel_set_vi_aa(bool e) { o_vi_aa = e; }
void parallel_set_vi_scale(bool e) { o_vi_scale = e; }
void parallel_set_dither_filter(bool e) { o_dither = e; }
void parallel_set_interlacing(bool weave) { o_weave = weave; }
void parallel_set_native_texture_lod(bool e) { o_native_lod = e; }
void parallel_set_native_tex_rect(bool e) { o_native_texrect = e; }

/* ---- Mupen64Plus graphics-plugin entry points (prefix "parallel", see DEFINE_GFX in plugin.c) ---- */

m64p_error parallelPluginGetVersion(m64p_plugin_type *type, int *version, int *api, const char **name, int *caps)
{
	if (type) *type = M64PLUGIN_GFX;
	if (version) *version = 0x010000;
	if (api) *api = 0x020200;
	if (name) *name = "Retro-Recomp parallel-rdp glue";
	if (caps) *caps = 0;
	return M64ERR_SUCCESS;
}

int parallelInitiateGFX(GFX_INFO info) { g_gfx = info; g_have_gfx = true; return 1; }
int parallelRomOpen(void) { parallel_init(); return 1; }   // the first initialisation waits for the ROM (GFX_INFO is known by then)
void parallelRomClosed(void) {}
void parallelChangeWindow(void) {}
void parallelMoveScreen(int, int) {}
void parallelProcessDList(void) {}     // display lists only reach the RDP through the LLE RSP
void parallelShowCFB(void) {}
void parallelViStatusChanged(void) {}
void parallelViWidthChanged(void) {}
void parallelSetRenderingCallback(void (*)(int)) {}
void parallelFBRead(unsigned int) {}
void parallelFBWrite(unsigned int, unsigned int) {}
void parallelFBGetFrameBufferInfo(void *) {}
void parallelReadScreen2(void *dest, int *width, int *height, int)
{
	if (width) *width = (int)g_width;
	if (height) *height = (int)g_height;
	(void)dest;   // screenshots go through the frontend's read-back
}

/* The RSP (or a CPU write to DPC_END) hands over the words between DPC_CURRENT and DPC_END, in RDRAM or in DMEM (XBUS).
   Complete commands go to parallel-rdp; a command cut at the end waits for the rest. A full sync raises the DP interrupt,
   after the GPU has finished when the synchronous mode is on (RDRAM is then up to date when the game sees it). */
void parallelProcessRDPList(void)
{
	if (!g_have_gfx)
		return;
	uint32_t cur = *g_gfx.DPC_CURRENT_REG & 0x00fffff8u, end = *g_gfx.DPC_END_REG & 0x00fffff8u;
	bool xbus = (*g_gfx.DPC_STATUS_REG & DPC_STATUS_XBUS_DMEM) != 0;
	const uint32_t *src = reinterpret_cast<const uint32_t *>(xbus ? g_gfx.DMEM : g_gfx.RDRAM);
	uint32_t mask = xbus ? 0xfffu : 0x7fffffu;
	for (uint32_t a = cur; a < end; a += 4)
		g_words.push_back(src[(a & mask) >> 2]);

	size_t i = 0;
	while (g_words.size() - i >= 2) {
		uint32_t op = (g_words[i] >> 24) & 63;
		size_t len = 2 * command_length(op);
		if (g_words.size() - i < len)
			break;
		if (op >= 8 && g_rdp)
			g_rdp->enqueue_command(unsigned(len), &g_words[i]);
		if (op == RDP_SYNC_FULL) {
			if (o_sync && g_rdp)
				g_rdp->wait_for_timeline(g_rdp->signal_timeline());
			*g_gfx.MI_INTR_REG |= MI_INTR_DP;
			g_gfx.CheckInterrupts();
		}
		i += len;
	}
	g_words.erase(g_words.begin(), g_words.begin() + ptrdiff_t(i));
	*g_gfx.DPC_START_REG = *g_gfx.DPC_CURRENT_REG = *g_gfx.DPC_END_REG;
}

/* One VI scan-out per vertical interrupt: the VI registers go to parallel-rdp, the scanned image goes to the frontend. */
void parallelUpdateScreen(void)
{
	if (!g_rdp || !g_vk)
		return;
	g_vk->wait_sync_index(g_vk->handle);
	unsigned index = g_vk->get_sync_index(g_vk->handle);
	if (index >= g_held.size())
		index = 0;

	const struct { RDP::VIRegister reg; unsigned int *src; } vi[] = {
		{RDP::VIRegister::Control, g_gfx.VI_STATUS_REG}, {RDP::VIRegister::Origin, g_gfx.VI_ORIGIN_REG},
		{RDP::VIRegister::Width, g_gfx.VI_WIDTH_REG}, {RDP::VIRegister::Intr, g_gfx.VI_INTR_REG},
		{RDP::VIRegister::VCurrentLine, g_gfx.VI_V_CURRENT_LINE_REG}, {RDP::VIRegister::Timing, g_gfx.VI_TIMING_REG},
		{RDP::VIRegister::VSync, g_gfx.VI_V_SYNC_REG}, {RDP::VIRegister::HSync, g_gfx.VI_H_SYNC_REG},
		{RDP::VIRegister::Leap, g_gfx.VI_LEAP_REG}, {RDP::VIRegister::HStart, g_gfx.VI_H_START_REG},
		{RDP::VIRegister::VStart, g_gfx.VI_V_START_REG}, {RDP::VIRegister::VBurst, g_gfx.VI_V_BURST_REG},
		{RDP::VIRegister::XScale, g_gfx.VI_X_SCALE_REG}, {RDP::VIRegister::YScale, g_gfx.VI_Y_SCALE_REG}};
	for (const auto &r : vi)
		g_rdp->set_vi_register(r.reg, *r.src);

	RDP::ScanoutOptions opts = {};
	opts.crop_overscan_pixels = o_overscan;
	opts.downscale_steps = o_downscale;
	opts.persist_frame_on_invalid_input = true;
	opts.upscale_deinterlacing = !o_weave;
	opts.vi.aa = o_vi_aa;
	opts.vi.scale = o_vi_scale;
	opts.vi.dither_filter = o_dither;
	opts.vi.divot_filter = o_divot;
	opts.vi.gamma_dither = o_gamma;
	Vulkan::ImageHandle image = g_rdp->scanout(opts);

	if (image) {
		retro_vulkan_image &out = g_images[index];
		out = {};
		out.image_view = image->get_view().get_view();
		out.image_layout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
		out.create_info.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
		out.create_info.image = image->get_image();
		out.create_info.viewType = VK_IMAGE_VIEW_TYPE_2D;
		out.create_info.format = image->get_format();
		out.create_info.components = {VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_B, VK_COMPONENT_SWIZZLE_A};
		out.create_info.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
		g_vk->set_image(g_vk->handle, &out, 0, nullptr, VK_QUEUE_FAMILY_IGNORED);
		g_held[index] = image;
		g_width = image->get_width();
		g_height = image->get_height();
		g_valid = true;
	} else {
		g_valid = false;
	}
	libretro_swap_buffer = true;
	g_rdp->begin_frame_context();
}

} // extern "C"
