/* Retro-Recomp Nintendo 64: C interface between the libretro glue (libretro.c) and the ParaLLEl-RDP renderer.
 * Copyright (c) 2026 Retro-Recomp contributors. SPDX-License-Identifier: MIT
 * Written from the call sites in libretro.c and the public parallel-rdp API; it replaces an unmarked header of the same name. */
#ifndef RR_N64_PARALLEL_H
#define RR_N64_PARALLEL_H

#include <stdbool.h>
#include <stdint.h>
#ifndef VK_NO_PROTOTYPES
#define VK_NO_PROTOTYPES   /* types only: the functions come from volk */
#endif
#include "libretro.h"
#include "libretro_vulkan.h"

#ifdef __cplusplus
extern "C" {
#endif

bool parallel_create_device(struct retro_vulkan_context *context, VkInstance instance, VkPhysicalDevice gpu,
                            VkSurfaceKHR surface, PFN_vkGetInstanceProcAddr get_instance_proc_addr,
                            const char **required_device_extensions, unsigned num_required_device_extensions,
                            const char **required_device_layers, unsigned num_required_device_layers,
                            const VkPhysicalDeviceFeatures *required_features);
const VkApplicationInfo *parallel_get_application_info(void);
void parallel_set_vulkan_interface(const struct retro_hw_render_interface_vulkan *vulkan);
bool parallel_init(void);
void parallel_deinit(void);

bool parallel_frame_is_valid(void);
unsigned parallel_frame_width(void);
unsigned parallel_frame_height(void);
void parallel_get_geometry(struct retro_game_geometry *geometry);
void parallel_profile_video_refresh_begin(void);
void parallel_profile_video_refresh_end(void);

/* Retro-Recomp: record RDP commands on parallel-rdp's worker thread (faster, not deterministic); before parallel_init. */
void parallel_set_threaded_commands(bool enable);
/* Retro-Recomp: wait until the GPU has finished every command recorded so far (before RDRAM is hashed). */
void parallel_quiesce(void);
void parallel_set_synchronous_rdp(bool enable);
void parallel_set_upscaling(unsigned factor, bool super_sampled);
void parallel_set_super_sampled_read_back_dither(bool enable);
void parallel_set_downscaling_steps(unsigned steps);
void parallel_set_overscan_crop(unsigned pixels);
void parallel_set_divot_filter(bool enable);
void parallel_set_gamma_dither(bool enable);
void parallel_set_vi_aa(bool enable);
void parallel_set_vi_scale(bool enable);
void parallel_set_dither_filter(bool enable);
void parallel_set_interlacing(bool weave);
void parallel_set_native_texture_lod(bool enable);
void parallel_set_native_tex_rect(bool enable);

#ifdef __cplusplus
}
#endif
#endif
