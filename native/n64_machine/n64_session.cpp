// Retro-Recomp Nintendo 64 session (n64_session.h). Original Retro-Recomp code, MIT; linked with Mupen64Plus-Next, the program is
// GPL-3.0 as a whole (licenses/mupen64plus-next.md).
//
// The libretro frontend of the statically linked core: fixed options answered here, a Vulkan 1.1 device created through the
// core's context negotiation without a surface, each finished frame copied from the renderer's image into a host-visible buffer
// kept between frames (the picture), the sound gathered per frame, the pads and sticks given when the core polls, the rumble kept
// per player. Nothing of the host (files, clock, configuration) reaches the machine.
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <mutex>
#include <string>
#include <vector>
#include "volk.h"
#include "libretro.h"
#include "libretro_vulkan.h"
#include "n64_session.h"
#include "n64_cpu.h"

extern "C" {
void parallel_quiesce(void);
void parallel_set_threaded_commands(bool enable);
bool parallel_init(void);
}

namespace {
constexpr uint64_t FNV_BASIS = 1469598103934665603ull, FNV_PRIME = 1099511628211ull;
constexpr char STATE_MAGIC[8] = {'R', 'R', 'N', '6', '4', 'Q', 'S', '1'};

uint64_t fnv(const void *data, size_t size, uint64_t h = FNV_BASIS)
{
    const uint8_t *p = static_cast<const uint8_t *>(data);
    for (size_t i = 0; i < size; ++i) h = (h ^ p[i]) * FNV_PRIME;
    return h;
}

// The same fold over 64-bit words (eight times fewer steps: 8 MiB of RDRAM a frame); a tail shorter than a word goes byte by byte.
uint64_t fnv_words(const void *data, size_t size)
{
    const uint8_t *p = static_cast<const uint8_t *>(data);
    uint64_t h = FNV_BASIS, word;
    size_t i = 0;
    for (; i + 8 <= size; i += 8) { memcpy(&word, p + i, 8); h = (h ^ word) * FNV_PRIME; }
    return fnv(p + i, size - i, h);
}
}

struct RrN64Session {
    RrN64Game game {};
    std::vector<uint8_t> rom;
    std::map<std::string, std::string> options;
    bool options_changed = false, renderer_reset = false;
    std::string error, gpu_name;
    void (*log)(const char *) = nullptr;

    // Vulkan
    const retro_hw_render_context_negotiation_interface_vulkan *negotiation = nullptr;
    retro_hw_render_callback hw {};
    retro_hw_render_interface_vulkan vk {};
    retro_vulkan_context context {};
    VkInstance instance = VK_NULL_HANDLE;
    std::mutex queue_lock;
    retro_vulkan_image image {};
    bool have_image = false;
    // the read-back buffer, kept while the picture keeps its size
    VkBuffer buffer = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    VkDeviceSize buffer_size = 0;
    void *mapped = nullptr;
    bool coherent = true;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkCommandBuffer commands = VK_NULL_HANDLE;
    VkFence fence = VK_NULL_HANDLE;

    // the frame
    std::vector<uint32_t> picture;
    int width = 0, height = 0;
    bool frame_new = false;
    std::vector<int16_t> audio;   // this frame's sound, interleaved stereo
    size_t audio_taken = 0;
    uint64_t frame = 0, video_hash = FNV_BASIS, pcm_hash = FNV_BASIS, ram_hash = 0, cpu_hash = 0;
    double fps = 60.0, aspect = 4.0 / 3.0;
    unsigned audio_rate = 44100;
    unsigned pads[4] {};
    int16_t sticks[4][4] {};
    uint16_t rumble[4][2] {};
};

namespace {
RrN64Session *g_session;   // the core keeps its state in globals: one session per process

void core_log(enum retro_log_level level, const char *format, ...)
{
    if (!g_session || !g_session->log || level < RETRO_LOG_WARN) return;
    char line[1024];
    va_list ap;
    va_start(ap, format);
    vsnprintf(line, sizeof line, format, ap);
    va_end(ap);
    g_session->log(line);
}

// ---- the Vulkan interface given to the core
void vk_set_image(void *, const retro_vulkan_image *image, uint32_t, const VkSemaphore *, uint32_t)
{
    g_session->image = *image;
    g_session->have_image = true;
}
uint32_t vk_get_sync_index(void *) { return 0; }
uint32_t vk_get_sync_index_mask(void *) { return 1u; }
void vk_set_command_buffers(void *, uint32_t count, const VkCommandBuffer *buffers)
{
    VkSubmitInfo submit = {VK_STRUCTURE_TYPE_SUBMIT_INFO};
    submit.commandBufferCount = count;
    submit.pCommandBuffers = buffers;
    std::lock_guard<std::mutex> lock(g_session->queue_lock);
    vkQueueSubmit(g_session->context.queue, 1, &submit, VK_NULL_HANDLE);
}
void vk_wait_sync_index(void *) {}
void vk_lock_queue(void *) { g_session->queue_lock.lock(); }
void vk_unlock_queue(void *) { g_session->queue_lock.unlock(); }
void vk_set_signal_semaphore(void *, VkSemaphore) {}

bool init_vulkan(RrN64Session *s)
{
    if (volkInitialize() != VK_SUCCESS) { s->error = "No Vulkan loader on this computer."; return false; }
    VkApplicationInfo app = {VK_STRUCTURE_TYPE_APPLICATION_INFO};
    app.pApplicationName = "Retro-Recomp N64";
    app.apiVersion = VK_API_VERSION_1_1;
    const VkApplicationInfo *wanted = s->negotiation && s->negotiation->get_application_info ? s->negotiation->get_application_info() : nullptr;
    if (wanted) app = *wanted;
    if (app.apiVersion < VK_API_VERSION_1_1) app.apiVersion = VK_API_VERSION_1_1;
    VkInstanceCreateInfo info = {VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    info.pApplicationInfo = &app;
    if (vkCreateInstance(&info, nullptr, &s->instance) != VK_SUCCESS) { s->error = "Vulkan 1.1 is not available."; return false; }
    volkLoadInstance(s->instance);
    uint32_t count = 0;
    vkEnumeratePhysicalDevices(s->instance, &count, nullptr);
    std::vector<VkPhysicalDevice> gpus(count);
    vkEnumeratePhysicalDevices(s->instance, &count, gpus.data());
    if (!count) { s->error = "No Vulkan graphics device."; return false; }
    // A named device, else the first discrete GPU, else the first device.
    VkPhysicalDevice gpu = gpus[0];
    bool chosen = false;
    for (auto g : gpus) {
        VkPhysicalDeviceProperties p;
        vkGetPhysicalDeviceProperties(g, &p);
        const bool match = s->game.gpu ? strstr(p.deviceName, s->game.gpu) != nullptr : p.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU;
        if (match && !chosen) { gpu = g; chosen = true; }
    }
    VkPhysicalDeviceProperties props;
    vkGetPhysicalDeviceProperties(gpu, &props);
    s->gpu_name = props.deviceName;
    if (!s->negotiation || !s->negotiation->create_device) { s->error = "The renderer gave no Vulkan device."; return false; }
    static VkPhysicalDeviceFeatures no_features = {};   // the core reads it
    if (!s->negotiation->create_device(&s->context, s->instance, gpu, VK_NULL_HANDLE, vkGetInstanceProcAddr, nullptr, 0, nullptr, 0,
                                       &no_features)) {
        s->error = "The Vulkan device lacks what the renderer needs (Vulkan 1.1).";
        return false;
    }
    volkLoadDevice(s->context.device);
    auto &v = s->vk;
    v.interface_type = RETRO_HW_RENDER_INTERFACE_VULKAN;
    v.interface_version = RETRO_HW_RENDER_INTERFACE_VULKAN_VERSION;
    v.handle = &v;
    v.instance = s->instance;
    v.gpu = s->context.gpu;
    v.device = s->context.device;
    v.get_device_proc_addr = vkGetDeviceProcAddr;
    v.get_instance_proc_addr = vkGetInstanceProcAddr;
    v.queue = s->context.queue;
    v.queue_index = s->context.queue_family_index;
    v.set_image = vk_set_image;
    v.get_sync_index = vk_get_sync_index;
    v.get_sync_index_mask = vk_get_sync_index_mask;
    v.set_command_buffers = vk_set_command_buffers;
    v.wait_sync_index = vk_wait_sync_index;
    v.lock_queue = vk_lock_queue;
    v.unlock_queue = vk_unlock_queue;
    v.set_signal_semaphore = vk_set_signal_semaphore;
    VkCommandPoolCreateInfo pool = {VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    pool.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    pool.queueFamilyIndex = s->context.queue_family_index;
    vkCreateCommandPool(s->context.device, &pool, nullptr, &s->pool);
    VkCommandBufferAllocateInfo alloc = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    alloc.commandPool = s->pool;
    alloc.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    alloc.commandBufferCount = 1;
    vkAllocateCommandBuffers(s->context.device, &alloc, &s->commands);
    VkFenceCreateInfo fence = {VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    vkCreateFence(s->context.device, &fence, nullptr, &s->fence);
    return s->pool && s->commands && s->fence;
}

bool ensure_buffer(RrN64Session *s, VkDeviceSize size)
{
    VkDevice d = s->context.device;
    if (s->buffer && s->buffer_size >= size) return true;
    if (s->buffer) { vkUnmapMemory(d, s->memory); vkDestroyBuffer(d, s->buffer, nullptr); vkFreeMemory(d, s->memory, nullptr); }
    s->buffer = VK_NULL_HANDLE; s->memory = VK_NULL_HANDLE; s->mapped = nullptr; s->buffer_size = 0;
    VkBufferCreateInfo info = {VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
    info.size = size;
    info.usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    if (vkCreateBuffer(d, &info, nullptr, &s->buffer) != VK_SUCCESS) return false;
    VkMemoryRequirements req;
    vkGetBufferMemoryRequirements(d, s->buffer, &req);
    VkPhysicalDeviceMemoryProperties props;
    vkGetPhysicalDeviceMemoryProperties(s->context.gpu, &props);
    // Host-cached memory first: the picture is read by the CPU, and uncached (write-combined) memory is very slow to read.
    const VkMemoryPropertyFlags wants[] = {
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_CACHED_BIT,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT};
    uint32_t type = UINT32_MAX;
    for (VkMemoryPropertyFlags want : wants)
        for (uint32_t i = 0; i < props.memoryTypeCount && type == UINT32_MAX; ++i)
            if ((req.memoryTypeBits & (1u << i)) && (props.memoryTypes[i].propertyFlags & want) == want) {
                type = i;
                s->coherent = (props.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) != 0;
            }
    if (type == UINT32_MAX) return false;
    VkMemoryAllocateInfo alloc = {VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    alloc.allocationSize = req.size;
    alloc.memoryTypeIndex = type;
    if (vkAllocateMemory(d, &alloc, nullptr, &s->memory) != VK_SUCCESS) return false;
    vkBindBufferMemory(d, s->buffer, s->memory, 0);
    if (vkMapMemory(d, s->memory, 0, size, 0, &s->mapped) != VK_SUCCESS) return false;
    s->buffer_size = size;
    return true;
}

// The renderer's image copied into the picture (0x00RRGGBB).
bool read_back(RrN64Session *s, unsigned w, unsigned h)
{
    if (!s->have_image || !w || !h || !ensure_buffer(s, VkDeviceSize(w) * h * 4)) return false;
    VkDevice d = s->context.device;
    const auto &img = s->image;
    vkResetCommandBuffer(s->commands, 0);
    VkCommandBufferBeginInfo begin = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    vkBeginCommandBuffer(s->commands, &begin);
    VkImageMemoryBarrier b = {VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
    b.srcAccessMask = VK_ACCESS_MEMORY_WRITE_BIT;
    b.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    b.oldLayout = img.image_layout;
    b.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    b.srcQueueFamilyIndex = b.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    b.image = img.create_info.image;
    b.subresourceRange = img.create_info.subresourceRange;
    vkCmdPipelineBarrier(s->commands, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 0, nullptr, 1, &b);
    VkBufferImageCopy region = {};
    region.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    region.imageSubresource.layerCount = 1;
    region.imageExtent = {w, h, 1};
    vkCmdCopyImageToBuffer(s->commands, img.create_info.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, s->buffer, 1, &region);
    b.srcAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    b.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
    b.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    b.newLayout = img.image_layout;
    vkCmdPipelineBarrier(s->commands, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 0, nullptr, 0, nullptr, 1, &b);
    vkEndCommandBuffer(s->commands);
    VkSubmitInfo submit = {VK_STRUCTURE_TYPE_SUBMIT_INFO};
    submit.commandBufferCount = 1;
    submit.pCommandBuffers = &s->commands;
    {
        std::lock_guard<std::mutex> lock(s->queue_lock);
        if (vkQueueSubmit(s->context.queue, 1, &submit, s->fence) != VK_SUCCESS) return false;
    }
    const VkResult waited = vkWaitForFences(d, 1, &s->fence, VK_TRUE, 5000000000ull);
    vkResetFences(d, 1, &s->fence);
    if (waited != VK_SUCCESS) return false;
    if (!s->coherent) {
        VkMappedMemoryRange range = {VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE};
        range.memory = s->memory;
        range.size = VK_WHOLE_SIZE;
        vkInvalidateMappedMemoryRanges(d, 1, &range);
    }
    const bool bgra = img.create_info.format == VK_FORMAT_B8G8R8A8_UNORM || img.create_info.format == VK_FORMAT_B8G8R8A8_SRGB;
    const uint8_t *src = static_cast<const uint8_t *>(s->mapped);
    s->picture.resize(size_t(w) * h);
    for (size_t i = 0; i < size_t(w) * h; ++i) {
        const uint8_t *p = src + i * 4;
        s->picture[i] = bgra ? (uint32_t(p[2]) << 16 | uint32_t(p[1]) << 8 | p[0]) : (uint32_t(p[0]) << 16 | uint32_t(p[1]) << 8 | p[2]);
    }
    s->width = int(w);
    s->height = int(h);
    return true;
}

// ---- libretro callbacks
bool environment(unsigned command, void *data)
{
    RrN64Session *s = g_session;
    switch (command) {
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE:
        static_cast<retro_log_callback *>(data)->log = core_log;
        return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        auto *v = static_cast<retro_variable *>(data);
        auto it = s->options.find(v->key);
        if (it == s->options.end()) { v->value = nullptr; return false; }
        v->value = it->second.c_str();
        return true;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
        *static_cast<bool *>(data) = s->options_changed;
        s->options_changed = false;
        return true;
    case RETRO_ENVIRONMENT_SET_VARIABLES:   // "Description; default|other|...": the defaults of the keys not set by the session
        for (auto *v = static_cast<const retro_variable *>(data); v && v->key; ++v) {
            const char *semi = v->value ? strstr(v->value, "; ") : nullptr;
            if (!semi) continue;
            std::string values = semi + 2;
            if (!s->options.count(v->key)) s->options[v->key] = values.substr(0, values.find('|'));
        }
        return true;
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *static_cast<const char **>(data) = nullptr;   // nothing is read or written there: saves go through rr_n64_save_memory
        return false;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
        return true;
    case RETRO_ENVIRONMENT_SET_HW_RENDER: {
        auto *hw = static_cast<retro_hw_render_callback *>(data);
        if (hw->context_type != RETRO_HW_CONTEXT_VULKAN) return false;
        s->hw = *hw;
        return true;
    }
    case RETRO_ENVIRONMENT_SET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE:
        s->negotiation = static_cast<const retro_hw_render_context_negotiation_interface_vulkan *>(data);
        return true;
    case RETRO_ENVIRONMENT_GET_HW_RENDER_INTERFACE:
        *static_cast<const retro_hw_render_interface **>(data) = reinterpret_cast<const retro_hw_render_interface *>(&s->vk);
        return true;
    case RETRO_ENVIRONMENT_GET_RUMBLE_INTERFACE:
        static_cast<retro_rumble_interface *>(data)->set_rumble_state = [](unsigned port, retro_rumble_effect effect, uint16_t strength) {
            if (port < 4 && g_session) g_session->rumble[port][effect == RETRO_RUMBLE_STRONG ? 0 : 1] = strength;
            return true;
        };
        return true;
    case RETRO_ENVIRONMENT_GET_JIT_CAPABLE:
        *static_cast<bool *>(data) = true;
        return true;
    case RETRO_ENVIRONMENT_SET_GEOMETRY: {
        const auto *g = static_cast<const retro_game_geometry *>(data);
        if (g->aspect_ratio > 0) s->aspect = g->aspect_ratio;
        return true;
    }
    default:
        return false;
    }
}

void video_refresh(const void *data, unsigned w, unsigned h, size_t)
{
    if (data != RETRO_HW_FRAME_BUFFER_VALID) return;   // a repeated frame keeps the last picture
    RrN64Session *s = g_session;
    if (read_back(s, w, h)) s->frame_new = true;
}

void push_audio(const int16_t *data, size_t frames)
{
    RrN64Session *s = g_session;
    s->audio.insert(s->audio.end(), data, data + frames * 2);
    s->pcm_hash = fnv(data, frames * 4, s->pcm_hash);
}
void audio_sample(int16_t left, int16_t right) { const int16_t pair[2] = {left, right}; push_audio(pair, 1); }
size_t audio_batch(const int16_t *data, size_t frames) { push_audio(data, frames); return frames; }
void input_poll() {}
int16_t input_state(unsigned port, unsigned device, unsigned index, unsigned id)
{
    RrN64Session *s = g_session;
    if (port >= 4) return 0;
    if (device == RETRO_DEVICE_JOYPAD) {
        const unsigned bits = s->pads[port] & 0xffffu;
        if (id == RETRO_DEVICE_ID_JOYPAD_MASK) return int16_t(bits);
        return id < 16 ? int16_t((bits >> id) & 1u) : 0;
    }
    if (device == RETRO_DEVICE_ANALOG && index <= RETRO_DEVICE_INDEX_ANALOG_RIGHT && id <= RETRO_DEVICE_ID_ANALOG_Y)
        return s->sticks[port][index * 2 + id];
    return 0;
}
}

extern "C" {

RrN64Session *rr_n64_open(const RrN64Game *game, char *error, size_t error_size)
{
    auto fail = [&](const std::string &why) -> RrN64Session * {
        if (error && error_size) snprintf(error, error_size, "%s", why.c_str());
        return nullptr;
    };
    if (g_session) return fail("A Nintendo 64 session is already open in this process.");
    if (!game || !game->rom || game->rom_size < 0x101000) return fail("No cartridge image.");
    auto *s = new RrN64Session;
    g_session = s;
    s->game = *game;
    s->log = game->log;
    s->rom.assign(game->rom, game->rom + game->rom_size);
    // The core's options, fixed: the ParaLLEl renderer and RSP, the 8 MiB of the Expansion Pak, the native resolution; the CPU
    // mode the conversion asked for.
    auto &o = s->options;
    o["mupen64plus-rdp-plugin"] = "parallel";
    o["mupen64plus-rsp-plugin"] = "parallel";
    o["mupen64plus-cpucore"] = game->cpu == RR_N64_CPU_CACHED ? "cached_interpreter" : "pure_interpreter";
    o["mupen64plus-parallel-rdp-upscaling"] = "1x";
    o["mupen64plus-parallel-rdp-synchronous"] = "True";
    o["mupen64plus-ForceDisableExtraMem"] = "False";
    const char *pak = game->pak && *game->pak ? game->pak : "memory";
    for (const char *key : {"mupen64plus-pak1", "mupen64plus-pak2", "mupen64plus-pak3", "mupen64plus-pak4"}) o[key] = pak;
    rr_n64_cpu_mode = game->cpu == RR_N64_CPU_OBSERVE ? 1 : game->cpu == RR_N64_CPU_NATIVE ? 2 : 0;
    if (game->cpu == RR_N64_CPU_NATIVE && !rr_n64_block_count) return fail("This build has no native blocks.");
    if (game->cpu == RR_N64_CPU_OBSERVE && !rr_n64_set_observe(1)) return fail("Not enough memory for the observation.");
    parallel_set_threaded_commands(game->threaded_rdp != 0);

    retro_set_environment(environment);
    retro_set_video_refresh(video_refresh);
    retro_set_audio_sample(audio_sample);
    retro_set_audio_sample_batch(audio_batch);
    retro_set_input_poll(input_poll);
    retro_set_input_state(input_state);
    retro_init();
    retro_game_info info = {};
    info.path = "game.z64";
    info.data = s->rom.data();
    info.size = s->rom.size();
    if (!retro_load_game(&info)) return fail("The core refused this cartridge image.");
    if (!init_vulkan(s)) return fail(s->error);
    if (s->hw.context_reset) s->hw.context_reset();
    for (unsigned port = 0; port < 4; ++port) retro_set_controller_port_device(port, RETRO_DEVICE_JOYPAD);
    retro_system_av_info av = {};
    retro_get_system_av_info(&av);
    if (av.timing.fps > 0) s->fps = av.timing.fps;
    if (av.timing.sample_rate > 0) s->audio_rate = unsigned(av.timing.sample_rate + 0.5);
    if (av.geometry.aspect_ratio > 0) s->aspect = av.geometry.aspect_ratio;
    s->picture.assign(320 * 240, 0);
    s->width = 320;
    s->height = 240;
    return s;
}

void rr_n64_pad(RrN64Session *s, int player, unsigned bits, const int16_t sticks[4])
{
    if (!s || player < 0 || player >= 4) return;
    s->pads[player] = bits;
    for (int a = 0; a < 4; ++a) s->sticks[player][a] = sticks ? sticks[a] : 0;
}

int rr_n64_frame(RrN64Session *s)
{
    if (!s) return -1;
    s->audio.clear();
    s->audio_taken = 0;
    s->pcm_hash = FNV_BASIS;
    s->frame_new = false;
    retro_run();
    s->frame++;
    if (s->renderer_reset) {
        // The internal resolution is read when the renderer starts: a new renderer, between two frames, on the same Vulkan device
        // (the libretro context calls would drop the device, which only a frontend that recreates it may do).
        s->renderer_reset = false;
        {
            std::lock_guard<std::mutex> lock(s->queue_lock);
            vkQueueWaitIdle(s->context.queue);
        }
        s->have_image = false;
        if (!parallel_init()) {
            s->error = "The renderer could not start again with these graphics options.";
            return -1;
        }
    }
    // The evidence of the frame, once (headless checks only): the GPU has finished, then the picture, RDRAM and the CPU registers.
    if (s->game.evidence) {
        parallel_quiesce();
        s->video_hash = s->picture.empty() ? FNV_BASIS : fnv_words(s->picture.data(), s->picture.size() * 4);
        size_t ram_size = 0;
        const uint8_t *ram = rr_n64_rdram(s, &ram_size);
        s->ram_hash = ram ? fnv_words(ram, ram_size) : 0;
        s->cpu_hash = rr_n64_cpu_state_hash();
    }
    return 0;
}

uint64_t rr_n64_frame_index(const RrN64Session *s) { return s ? s->frame : 0; }

// The seed of the VI's dither noise (the adapted video_interface.cpp asks for it at each scanout): the session's frame number,
// which a quick state carries, instead of the renderer's own count since it started, which none does.
uint32_t rr_n64_vi_noise_frame(uint32_t own) { return g_session ? uint32_t(g_session->frame) : own; }

const char *rr_n64_error(const RrN64Session *s) { return s ? s->error.c_str() : "no session"; }

const uint32_t *rr_n64_picture(const RrN64Session *s, int *width, int *height)
{
    if (width) *width = s ? s->width : 0;
    if (height) *height = s ? s->height : 0;
    return s && !s->picture.empty() ? s->picture.data() : nullptr;
}
double rr_n64_aspect(const RrN64Session *s) { return s ? s->aspect : 4.0 / 3.0; }

size_t rr_n64_audio(RrN64Session *s, int16_t *pcm, size_t capacity_frames)
{
    if (!s) return 0;
    size_t frames = (s->audio.size() - s->audio_taken) / 2;
    if (frames > capacity_frames) frames = capacity_frames;
    memcpy(pcm, s->audio.data() + s->audio_taken, frames * 4);
    s->audio_taken += frames * 2;
    return frames;
}
unsigned rr_n64_audio_rate(const RrN64Session *s) { return s ? s->audio_rate : 44100; }
double rr_n64_fps(const RrN64Session *s) { return s ? s->fps : 60.0; }

int rr_n64_rumble(const RrN64Session *s, int player, uint16_t *strong, uint16_t *weak)
{
    if (!s || player < 0 || player >= 4) { if (strong) *strong = 0; if (weak) *weak = 0; return 0; }
    if (strong) *strong = s->rumble[player][0];
    if (weak) *weak = s->rumble[player][1];
    return s->rumble[player][0] || s->rumble[player][1];
}

int rr_n64_option(RrN64Session *s, const char *key, const char *value)
{
    if (!s || !key || !value) return 0;
    const std::string name = std::string("mupen64plus-") + key;
    if (!s->options.count(name)) return 0;
    if (s->options[name] == value) return 1;
    s->options[name] = value;
    s->options_changed = true;
    if (!strcmp(key, "parallel-rdp-upscaling") || !strcmp(key, "parallel-rdp-super-sampled-read-back")) s->renderer_reset = true;
    return 1;
}

void rr_n64_frame_info(const RrN64Session *s, RrN64FrameInfo *info)
{
    memset(info, 0, sizeof *info);
    if (!s) return;
    info->frame = s->frame;
    info->video = s->video_hash;
    info->pcm = s->pcm_hash;
    info->ram = s->ram_hash;
    info->cpu = s->cpu_hash;
    info->pc = rr_n64_cpu_pc();
    info->samples = uint32_t(s->audio.size() / 2);
    info->width = s->width;
    info->height = s->height;
    for (uint32_t c : s->picture) if (c & 0xffffffu) { info->nonblack = 1; break; }
    for (int16_t v : s->audio) if (v) { info->audible = 1; break; }
}

const uint8_t *rr_n64_rdram(const RrN64Session *, size_t *size)
{
    *size = retro_get_memory_size(RETRO_MEMORY_SYSTEM_RAM);
    return static_cast<const uint8_t *>(retro_get_memory_data(RETRO_MEMORY_SYSTEM_RAM));
}

uint8_t *rr_n64_save_memory(RrN64Session *, size_t *size)
{
    *size = retro_get_memory_size(RETRO_MEMORY_SAVE_RAM);
    return static_cast<uint8_t *>(retro_get_memory_data(RETRO_MEMORY_SAVE_RAM));
}

uint64_t rr_n64_interpreted_count(const RrN64Session *) { return ::rr_n64_interpreted; }
uint64_t rr_n64_native_count(const RrN64Session *) { return ::rr_n64_native; }
uint64_t rr_n64_block_entry_count(const RrN64Session *) { return ::rr_n64_block_entries; }
uint64_t rr_n64_guard_miss_count(const RrN64Session *) { return ::rr_n64_guard_misses; }
int rr_n64_observations_write(const RrN64Session *, void *file) { return ::rr_n64_write_observations(static_cast<FILE *>(file)); }
size_t rr_n64_observed_count(const RrN64Session *) { return ::rr_n64_observation_count(); }
const char *rr_n64_gpu_name(const RrN64Session *s) { return s ? s->gpu_name.c_str() : ""; }

// A state: the magic, the build's key (64 bytes), the session's frame, the core's own state.
int rr_n64_state_capture(RrN64Session *s, const char *abi, uint8_t **out, size_t *size)
{
    if (!s || !abi || !out || !size) return 4;
    const size_t core = retro_serialize_size();
    const size_t head = sizeof STATE_MAGIC + 64 + 8;
    uint8_t *data = static_cast<uint8_t *>(malloc(head + core));
    if (!data || !core) { free(data); return 4; }
    memcpy(data, STATE_MAGIC, sizeof STATE_MAGIC);
    memset(data + 8, 0, 64);
    memcpy(data + 8, abi, strnlen(abi, 64));
    memcpy(data + 72, &s->frame, 8);
    if (!retro_serialize(data + head, core)) { free(data); return 4; }
    *out = data;
    *size = head + core;
    return 0;
}

int rr_n64_state_restore(RrN64Session *s, const char *abi, const uint8_t *data, size_t size)
{
    const size_t head = sizeof STATE_MAGIC + 64 + 8;
    if (!s || !data || size <= head || memcmp(data, STATE_MAGIC, sizeof STATE_MAGIC)) return 3;
    char key[64] = {};
    memcpy(key, abi, strnlen(abi, 64));
    if (memcmp(data + 8, key, 64)) return 2;
    // The core starts its machine in the first frames it runs: a state loaded before them would land on nothing. Two frames
    // without input run first; the state then replaces all of the machine (the session's frame counter included).
    for (int warm = 0; s->frame == 0 && warm < 2; ++warm) {
        retro_run();
        s->audio.clear();
    }
    if (!retro_unserialize(data + head, size - head)) return 3;
    memcpy(&s->frame, data + 72, 8);
    return 0;
}

}
