/* A libretro frontend's Vulkan side, shared by the Nintendo 64 and the PlayStation (libretro_vulkan_host.h). Retro-Recomp's own
 * code, MIT. Moved out of native/n64_machine/n64_session.cpp in 1.7.7 with the same calls in the same order: the Nintendo 64's
 * pictures, sound, memory and states are byte for byte those of 1.7.6. */
#include "libretro_vulkan_host.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <SDL.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif

static RrVkHost *host_of(void *handle) { return (RrVkHost *)((char *)handle - offsetof(RrVkHost, vk)); }

static void lock(RrVkHost *h) { SDL_LockMutex((SDL_mutex *)h->queue_lock); }
static void unlock(RrVkHost *h) { SDL_UnlockMutex((SDL_mutex *)h->queue_lock); }

/* ---- the Vulkan interface given to the core */
static void vk_set_image(void *handle, const struct retro_vulkan_image *image, uint32_t n, const VkSemaphore *s, uint32_t q)
{
    RrVkHost *h = host_of(handle);
    (void)n; (void)s; (void)q;
    h->image = *image;
    h->have_image = 1;
}
static uint32_t vk_get_sync_index(void *handle) { (void)handle; return 0; }
static uint32_t vk_get_sync_index_mask(void *handle) { (void)handle; return 1u; }
static void vk_set_command_buffers(void *handle, uint32_t count, const VkCommandBuffer *buffers)
{
    RrVkHost *h = host_of(handle);
    VkSubmitInfo submit;
    memset(&submit, 0, sizeof submit);
    submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submit.commandBufferCount = count;
    submit.pCommandBuffers = buffers;
    lock(h);
    h->f.QueueSubmit(h->context.queue, 1, &submit, VK_NULL_HANDLE);
    unlock(h);
}
static void vk_wait_sync_index(void *handle) { (void)handle; }
static void vk_lock_queue(void *handle) { lock(host_of(handle)); }
static void vk_unlock_queue(void *handle) { unlock(host_of(handle)); }
static void vk_set_signal_semaphore(void *handle, VkSemaphore semaphore) { (void)handle; (void)semaphore; }

PFN_vkGetInstanceProcAddr rr_vk_host_loader(void)
{
    static PFN_vkGetInstanceProcAddr found;
    static int tried;
    if (tried) return found;
    tried = 1;
#ifdef _WIN32
    HMODULE library = LoadLibraryA("vulkan-1.dll");
    if (library) found = (PFN_vkGetInstanceProcAddr)(void (*)(void))GetProcAddress(library, "vkGetInstanceProcAddr");
#else
    void *library = dlopen("libvulkan.so.1", RTLD_NOW | RTLD_LOCAL);
    if (!library) library = dlopen("libvulkan.so", RTLD_NOW | RTLD_LOCAL);
    if (library) found = (PFN_vkGetInstanceProcAddr)dlsym(library, "vkGetInstanceProcAddr");
#endif
    return found;
}

int rr_vk_host_environment(RrVkHost *h, unsigned command, void *data, int *answer)
{
    switch (command) {
    case RETRO_ENVIRONMENT_SET_HW_RENDER: {
        const struct retro_hw_render_callback *hw = (const struct retro_hw_render_callback *)data;
        if (hw->context_type != RETRO_HW_CONTEXT_VULKAN) { *answer = 0; return 1; }
        h->hw = *hw;
        *answer = 1;
        return 1;
    }
    case RETRO_ENVIRONMENT_SET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE:
        h->negotiation = (const struct retro_hw_render_context_negotiation_interface_vulkan *)data;
        *answer = 1;
        return 1;
    case RETRO_ENVIRONMENT_GET_HW_RENDER_INTERFACE:
        *(const struct retro_hw_render_interface **)data = (const struct retro_hw_render_interface *)&h->vk;
        *answer = 1;
        return 1;
    default:
        return 0;
    }
}

#define INSTANCE_FUNCTION(name) (h->f.name = (PFN_vk##name)h->get_instance_proc_addr(h->instance, "vk" #name))
#define DEVICE_FUNCTION(name) (h->f.name = (PFN_vk##name)h->f.GetDeviceProcAddr(h->context.device, "vk" #name))

int rr_vk_host_open(RrVkHost *h, PFN_vkGetInstanceProcAddr gipa, const char *app_name, const char *wanted_gpu,
                    RrVkInstanceHook on_instance, RrVkDeviceHook on_device)
{
    h->get_instance_proc_addr = gipa;
    if (!gipa) { h->error = "No Vulkan loader on this computer."; return 0; }
    if (!h->queue_lock && !(h->queue_lock = SDL_CreateMutex())) { h->error = "Vulkan could not be set up (no lock)."; return 0; }
    h->f.CreateInstance = (PFN_vkCreateInstance)gipa(VK_NULL_HANDLE, "vkCreateInstance");
    if (!h->f.CreateInstance) { h->error = "No Vulkan loader on this computer."; return 0; }
    VkApplicationInfo app;
    memset(&app, 0, sizeof app);
    app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    app.pApplicationName = app_name;
    app.apiVersion = VK_API_VERSION_1_1;
    const VkApplicationInfo *wanted = h->negotiation && h->negotiation->get_application_info ? h->negotiation->get_application_info() : NULL;
    if (wanted) app = *wanted;
    if (app.apiVersion < VK_API_VERSION_1_1) app.apiVersion = VK_API_VERSION_1_1;
    VkInstanceCreateInfo info;
    memset(&info, 0, sizeof info);
    info.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    info.pApplicationInfo = &app;
    if (h->f.CreateInstance(&info, NULL, &h->instance) != VK_SUCCESS) { h->error = "Vulkan 1.1 is not available."; return 0; }
    if (on_instance) on_instance(h->instance);
    INSTANCE_FUNCTION(EnumeratePhysicalDevices);
    INSTANCE_FUNCTION(GetPhysicalDeviceProperties);
    INSTANCE_FUNCTION(GetPhysicalDeviceMemoryProperties);
    INSTANCE_FUNCTION(GetDeviceProcAddr);
    if (!h->f.EnumeratePhysicalDevices || !h->f.GetPhysicalDeviceProperties || !h->f.GetPhysicalDeviceMemoryProperties || !h->f.GetDeviceProcAddr) {
        h->error = "Vulkan 1.1 is not available.";
        return 0;
    }
    uint32_t count = 0;
    h->f.EnumeratePhysicalDevices(h->instance, &count, NULL);
    VkPhysicalDevice *gpus = count ? (VkPhysicalDevice *)calloc(count, sizeof *gpus) : NULL;
    if (gpus) h->f.EnumeratePhysicalDevices(h->instance, &count, gpus);
    if (!count || !gpus) { free(gpus); h->error = "No Vulkan graphics device."; return 0; }
    /* A named device, else the first discrete GPU, else the first device. */
    VkPhysicalDevice gpu = gpus[0];
    int chosen = 0;
    for (uint32_t i = 0; i < count; ++i) {
        VkPhysicalDeviceProperties p;
        h->f.GetPhysicalDeviceProperties(gpus[i], &p);
        const int match = wanted_gpu ? strstr(p.deviceName, wanted_gpu) != NULL : p.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU;
        if (match && !chosen) { gpu = gpus[i]; chosen = 1; }
    }
    free(gpus);
    VkPhysicalDeviceProperties props;
    h->f.GetPhysicalDeviceProperties(gpu, &props);
    snprintf(h->gpu_name, sizeof h->gpu_name, "%s", props.deviceName);
    if (!h->negotiation || !h->negotiation->create_device) { h->error = "The renderer gave no Vulkan device."; return 0; }
    static VkPhysicalDeviceFeatures no_features;   /* the core reads it */
    if (!h->negotiation->create_device(&h->context, h->instance, gpu, VK_NULL_HANDLE, gipa, NULL, 0, NULL, 0, &no_features)) {
        h->error = "The Vulkan device lacks what the renderer needs (Vulkan 1.1).";
        return 0;
    }
    if (on_device) on_device(h->context.device);
    DEVICE_FUNCTION(QueueSubmit);
    DEVICE_FUNCTION(QueueWaitIdle);
    DEVICE_FUNCTION(CreateCommandPool);
    DEVICE_FUNCTION(AllocateCommandBuffers);
    DEVICE_FUNCTION(CreateFence);
    DEVICE_FUNCTION(WaitForFences);
    DEVICE_FUNCTION(ResetFences);
    DEVICE_FUNCTION(CreateBuffer);
    DEVICE_FUNCTION(DestroyBuffer);
    DEVICE_FUNCTION(GetBufferMemoryRequirements);
    DEVICE_FUNCTION(AllocateMemory);
    DEVICE_FUNCTION(FreeMemory);
    DEVICE_FUNCTION(BindBufferMemory);
    DEVICE_FUNCTION(MapMemory);
    DEVICE_FUNCTION(UnmapMemory);
    DEVICE_FUNCTION(InvalidateMappedMemoryRanges);
    DEVICE_FUNCTION(ResetCommandBuffer);
    DEVICE_FUNCTION(BeginCommandBuffer);
    DEVICE_FUNCTION(EndCommandBuffer);
    DEVICE_FUNCTION(CmdPipelineBarrier);
    DEVICE_FUNCTION(CmdCopyImageToBuffer);
    DEVICE_FUNCTION(DeviceWaitIdle);
    DEVICE_FUNCTION(DestroyCommandPool);
    DEVICE_FUNCTION(DestroyFence);
    DEVICE_FUNCTION(DestroyDevice);
    INSTANCE_FUNCTION(DestroyInstance);
    struct retro_hw_render_interface_vulkan *v = &h->vk;
    v->interface_type = RETRO_HW_RENDER_INTERFACE_VULKAN;
    v->interface_version = RETRO_HW_RENDER_INTERFACE_VULKAN_VERSION;
    v->handle = v;
    v->instance = h->instance;
    v->gpu = h->context.gpu;
    v->device = h->context.device;
    v->get_device_proc_addr = h->f.GetDeviceProcAddr;
    v->get_instance_proc_addr = gipa;
    v->queue = h->context.queue;
    v->queue_index = h->context.queue_family_index;
    v->set_image = vk_set_image;
    v->get_sync_index = vk_get_sync_index;
    v->get_sync_index_mask = vk_get_sync_index_mask;
    v->set_command_buffers = vk_set_command_buffers;
    v->wait_sync_index = vk_wait_sync_index;
    v->lock_queue = vk_lock_queue;
    v->unlock_queue = vk_unlock_queue;
    v->set_signal_semaphore = vk_set_signal_semaphore;
    VkCommandPoolCreateInfo pool;
    memset(&pool, 0, sizeof pool);
    pool.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
    pool.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    pool.queueFamilyIndex = h->context.queue_family_index;
    h->f.CreateCommandPool(h->context.device, &pool, NULL, &h->pool);
    VkCommandBufferAllocateInfo alloc;
    memset(&alloc, 0, sizeof alloc);
    alloc.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    alloc.commandPool = h->pool;
    alloc.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    alloc.commandBufferCount = 1;
    h->f.AllocateCommandBuffers(h->context.device, &alloc, &h->commands);
    VkFenceCreateInfo fence;
    memset(&fence, 0, sizeof fence);
    fence.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
    h->f.CreateFence(h->context.device, &fence, NULL, &h->fence);
    return h->pool && h->commands && h->fence;
}

static int ensure_buffer(RrVkHost *h, VkDeviceSize size)
{
    VkDevice d = h->context.device;
    if (h->buffer && h->buffer_size >= size) return 1;
    if (h->buffer) { h->f.UnmapMemory(d, h->memory); h->f.DestroyBuffer(d, h->buffer, NULL); h->f.FreeMemory(d, h->memory, NULL); }
    h->buffer = VK_NULL_HANDLE; h->memory = VK_NULL_HANDLE; h->mapped = NULL; h->buffer_size = 0;
    VkBufferCreateInfo info;
    memset(&info, 0, sizeof info);
    info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    info.size = size;
    info.usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    if (h->f.CreateBuffer(d, &info, NULL, &h->buffer) != VK_SUCCESS) return 0;
    VkMemoryRequirements req;
    h->f.GetBufferMemoryRequirements(d, h->buffer, &req);
    VkPhysicalDeviceMemoryProperties props;
    h->f.GetPhysicalDeviceMemoryProperties(h->context.gpu, &props);
    /* Host-cached memory first: the picture is read by the CPU, and uncached (write-combined) memory is very slow to read. */
    const VkMemoryPropertyFlags wants[] = {
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT};
    uint32_t type = UINT32_MAX;
    for (size_t w = 0; w < sizeof wants / sizeof wants[0]; ++w)
        for (uint32_t i = 0; i < props.memoryTypeCount && type == UINT32_MAX; ++i)
            if ((req.memoryTypeBits & (1u << i)) && (props.memoryTypes[i].propertyFlags & wants[w]) == wants[w]) {
                type = i;
                h->coherent = (props.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) != 0;
            }
    if (type == UINT32_MAX) return 0;
    VkMemoryAllocateInfo alloc;
    memset(&alloc, 0, sizeof alloc);
    alloc.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    alloc.allocationSize = req.size;
    alloc.memoryTypeIndex = type;
    if (h->f.AllocateMemory(d, &alloc, NULL, &h->memory) != VK_SUCCESS) return 0;
    h->f.BindBufferMemory(d, h->buffer, h->memory, 0);
    if (h->f.MapMemory(d, h->memory, 0, size, 0, &h->mapped) != VK_SUCCESS) return 0;
    h->buffer_size = size;
    return 1;
}

const uint8_t *rr_vk_host_read_back(RrVkHost *h, unsigned w, unsigned hgt, int *bgra)
{
    if (!h->have_image || !w || !hgt || !ensure_buffer(h, (VkDeviceSize)w * hgt * 4)) return NULL;
    VkDevice d = h->context.device;
    const struct retro_vulkan_image *img = &h->image;
    h->f.ResetCommandBuffer(h->commands, 0);
    VkCommandBufferBeginInfo begin;
    memset(&begin, 0, sizeof begin);
    begin.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    h->f.BeginCommandBuffer(h->commands, &begin);
    VkImageMemoryBarrier b;
    memset(&b, 0, sizeof b);
    b.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    b.srcAccessMask = VK_ACCESS_MEMORY_WRITE_BIT;
    b.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    b.oldLayout = img->image_layout;
    b.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    b.srcQueueFamilyIndex = b.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    b.image = img->create_info.image;
    b.subresourceRange = img->create_info.subresourceRange;
    h->f.CmdPipelineBarrier(h->commands, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &b);
    VkBufferImageCopy region;
    memset(&region, 0, sizeof region);
    region.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    region.imageSubresource.layerCount = 1;
    region.imageExtent.width = w;
    region.imageExtent.height = hgt;
    region.imageExtent.depth = 1;
    h->f.CmdCopyImageToBuffer(h->commands, img->create_info.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, h->buffer, 1, &region);
    b.srcAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    b.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
    b.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    b.newLayout = img->image_layout;
    h->f.CmdPipelineBarrier(h->commands, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 0, NULL, 0, NULL, 1, &b);
    h->f.EndCommandBuffer(h->commands);
    VkSubmitInfo submit;
    memset(&submit, 0, sizeof submit);
    submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submit.commandBufferCount = 1;
    submit.pCommandBuffers = &h->commands;
    lock(h);
    const VkResult submitted = h->f.QueueSubmit(h->context.queue, 1, &submit, h->fence);
    unlock(h);
    if (submitted != VK_SUCCESS) return NULL;
    const VkResult waited = h->f.WaitForFences(d, 1, &h->fence, VK_TRUE, 5000000000ull);
    h->f.ResetFences(d, 1, &h->fence);
    if (waited != VK_SUCCESS) return NULL;
    if (!h->coherent) {
        VkMappedMemoryRange range;
        memset(&range, 0, sizeof range);
        range.sType = VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE;
        range.memory = h->memory;
        range.size = VK_WHOLE_SIZE;
        h->f.InvalidateMappedMemoryRanges(d, 1, &range);
    }
    *bgra = img->create_info.format == VK_FORMAT_B8G8R8A8_UNORM || img->create_info.format == VK_FORMAT_B8G8R8A8_SRGB;
    return (const uint8_t *)h->mapped;
}

void rr_vk_host_picture(const uint8_t *src, int bgra, uint32_t *picture, size_t pixels)
{
    for (size_t i = 0; i < pixels; ++i) {
        const uint8_t *p = src + i * 4;
        picture[i] = bgra ? ((uint32_t)p[2] << 16 | (uint32_t)p[1] << 8 | p[0]) : ((uint32_t)p[0] << 16 | (uint32_t)p[1] << 8 | p[2]);
    }
}

void rr_vk_host_wait_idle(RrVkHost *h)
{
    lock(h);
    h->f.QueueWaitIdle(h->context.queue);
    unlock(h);
}

void rr_vk_host_close_context(RrVkHost *h)
{
    if (!h->context.device || !h->hw.context_destroy) return;
    rr_vk_host_wait_idle(h);
    h->hw.context_destroy();
    h->hw.context_destroy = NULL;
}

void rr_vk_host_close(RrVkHost *h)
{
    void *queue_lock = h->queue_lock;
    VkDevice d = h->context.device;
    if (d) {
        if (h->f.DeviceWaitIdle) h->f.DeviceWaitIdle(d);
        if (h->buffer) { h->f.UnmapMemory(d, h->memory); h->f.DestroyBuffer(d, h->buffer, NULL); h->f.FreeMemory(d, h->memory, NULL); }
        if (h->fence) h->f.DestroyFence(d, h->fence, NULL);
        if (h->pool) h->f.DestroyCommandPool(d, h->pool, NULL);   /* frees its command buffer */
        if (h->negotiation && h->negotiation->interface_version >= 2 && h->negotiation->destroy_device) h->negotiation->destroy_device();
        else if (h->f.DestroyDevice) h->f.DestroyDevice(d, NULL);
    }
    if (h->instance && h->f.DestroyInstance) h->f.DestroyInstance(h->instance, NULL);
    memset(h, 0, sizeof *h);
    h->queue_lock = queue_lock;
}
