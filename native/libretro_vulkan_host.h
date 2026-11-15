/* A libretro frontend's Vulkan side for a core that renders with Vulkan, shared by the Nintendo 64 (Mupen64Plus-Next with
 * ParaLLEl-RDP) and the PlayStation (Beetle PSX's Vulkan renderer). Retro-Recomp's own code, MIT.
 *
 * What it does, for one core per process: answers the core's hardware-render requests (SET_HW_RENDER for a Vulkan context, the
 * context negotiation interface, GET_HW_RENDER_INTERFACE), creates a Vulkan 1.1 instance and lets the core create its device
 * through the negotiation without a surface, gives the core the libretro Vulkan interface (its queue behind one lock, the image of
 * each frame kept), and copies each finished frame from the core's image into a host-visible buffer kept between frames (the
 * picture the host kit shows, 0x00RRGGBB). The Vulkan functions it calls are loaded through the vkGetInstanceProcAddr the caller
 * gives (a loader of its own, or rr_vk_host_loader()); nothing is linked against a Vulkan library.
 *
 * Compiled in each game against that game's own core headers (libretro.h, libretro_vulkan.h and the Vulkan headers they include). */
#ifndef LIBRETRO_VULKAN_HOST_H
#define LIBRETRO_VULKAN_HOST_H

#ifndef VK_NO_PROTOTYPES
#define VK_NO_PROTOTYPES
#endif
#include <stddef.h>
#include <stdint.h>
#include "libretro.h"
#include "libretro_vulkan.h"

#ifdef __cplusplus
extern "C" {
#endif

/* The functions this file calls, loaded through the caller's vkGetInstanceProcAddr (instance level) and the device's
 * vkGetDeviceProcAddr (device level). */
typedef struct RrVkFunctions {
    PFN_vkCreateInstance CreateInstance;
    PFN_vkEnumeratePhysicalDevices EnumeratePhysicalDevices;
    PFN_vkGetPhysicalDeviceProperties GetPhysicalDeviceProperties;
    PFN_vkGetPhysicalDeviceMemoryProperties GetPhysicalDeviceMemoryProperties;
    PFN_vkGetDeviceProcAddr GetDeviceProcAddr;
    PFN_vkQueueSubmit QueueSubmit;
    PFN_vkQueueWaitIdle QueueWaitIdle;
    PFN_vkCreateCommandPool CreateCommandPool;
    PFN_vkAllocateCommandBuffers AllocateCommandBuffers;
    PFN_vkCreateFence CreateFence;
    PFN_vkWaitForFences WaitForFences;
    PFN_vkResetFences ResetFences;
    PFN_vkCreateBuffer CreateBuffer;
    PFN_vkDestroyBuffer DestroyBuffer;
    PFN_vkGetBufferMemoryRequirements GetBufferMemoryRequirements;
    PFN_vkAllocateMemory AllocateMemory;
    PFN_vkFreeMemory FreeMemory;
    PFN_vkBindBufferMemory BindBufferMemory;
    PFN_vkMapMemory MapMemory;
    PFN_vkUnmapMemory UnmapMemory;
    PFN_vkInvalidateMappedMemoryRanges InvalidateMappedMemoryRanges;
    PFN_vkResetCommandBuffer ResetCommandBuffer;
    PFN_vkBeginCommandBuffer BeginCommandBuffer;
    PFN_vkEndCommandBuffer EndCommandBuffer;
    PFN_vkCmdPipelineBarrier CmdPipelineBarrier;
    PFN_vkCmdCopyImageToBuffer CmdCopyImageToBuffer;
    /* closing (rr_vk_host_close) */
    PFN_vkDeviceWaitIdle DeviceWaitIdle;
    PFN_vkDestroyCommandPool DestroyCommandPool;
    PFN_vkDestroyFence DestroyFence;
    PFN_vkDestroyDevice DestroyDevice;
    PFN_vkDestroyInstance DestroyInstance;
} RrVkFunctions;

typedef struct RrVkHost {
    /* what the core asked for and gave */
    const struct retro_hw_render_context_negotiation_interface_vulkan *negotiation;
    struct retro_hw_render_callback hw;
    struct retro_hw_render_interface_vulkan vk;
    struct retro_vulkan_context context;
    VkInstance instance;
    struct retro_vulkan_image image;     /* the core's image of the last frame */
    int have_image;
    /* the read-back buffer, kept while the picture keeps its size */
    VkBuffer buffer;
    VkDeviceMemory memory;
    VkDeviceSize buffer_size;
    void *mapped;
    int coherent;
    VkCommandPool pool;
    VkCommandBuffer commands;
    VkFence fence;
    void *queue_lock;                    /* an SDL_mutex: the core's submissions and ours go to one queue */
    PFN_vkGetInstanceProcAddr get_instance_proc_addr;
    RrVkFunctions f;
    char gpu_name[256];
    int gpu_type;                        /* the chosen device's VkPhysicalDeviceType */
    int refuse_cpu_device;               /* set before rr_vk_host_open: a device emulated on the CPU (llvmpipe) is no graphics card */
    const char *error;                   /* why rr_vk_host_open or a read-back failed, in the player's words */
} RrVkHost;

/* Called right after the instance, then the device, is created (the Nintendo 64 loads its own volk tables there). NULL: none. */
typedef void (*RrVkInstanceHook)(VkInstance instance);
typedef void (*RrVkDeviceHook)(VkDevice device);

/* The Vulkan loader of this computer (vulkan-1.dll, libvulkan.so.1), loaded once; NULL when there is none. */
PFN_vkGetInstanceProcAddr rr_vk_host_loader(void);

/* The core's hardware-render environment calls: 1 handled (its answer in *answer), 0 not one of them. */
int rr_vk_host_environment(RrVkHost *host, unsigned command, void *data, int *answer);

/* The instance (app_name, Vulkan 1.1 or what the core asks for), the device the core creates through its negotiation on the GPU
 * whose name holds `wanted_gpu` (NULL: the first discrete GPU, else the first integrated one, else a virtual one, else any other,
 * a device emulated on the CPU last), the interface given to the core, the command pool, buffer and fence of the read-back. 0 with
 * host->error set when Vulkan or a device is missing, or when only a CPU device is left and `refuse_cpu_device` is set. */
int rr_vk_host_open(RrVkHost *host, PFN_vkGetInstanceProcAddr get_instance_proc_addr, const char *app_name, const char *wanted_gpu,
                    RrVkInstanceHook on_instance, RrVkDeviceHook on_device);

/* The core's image of the last frame (w x h) copied to the read-back buffer; returns its bytes (w * h * 4, in the image's own
 * order) and whether that order is BGRA, or NULL when there is no image or the copy failed. */
const uint8_t *rr_vk_host_read_back(RrVkHost *host, unsigned w, unsigned h, int *bgra);

/* Those bytes as the host's picture (0x00RRGGBB). */
void rr_vk_host_picture(const uint8_t *bytes, int bgra, uint32_t *picture, size_t pixels);

/* Waits until the queue is idle (before the core starts its renderer again on the same device). */
void rr_vk_host_wait_idle(RrVkHost *host);

/* Everything opened, closed in the order libretro asks: the core's context (its context_destroy; call it after the core's last
 * frame, before retro_unload_game), then the read-back's own objects, the device (the core's destroy_device when it gives one,
 * else vkDestroyDevice), the instance. The host keeps its lock and can be opened again. Nothing happens when it was never opened. */
void rr_vk_host_close_context(RrVkHost *host);
void rr_vk_host_close(RrVkHost *host);

#ifdef __cplusplus
}
#endif

#endif
