/* The resource layout of a SPIR-V shader, for Beetle PSX's Vulkan renderer (Retro-Recomp's own code, MIT).
 *
 * Beetle's renderer asks one question of each of its prebuilt shaders, through rhi_spirv_reflect() (rhi/rhi_spirv_reflect.h):
 * which descriptor bindings, stage inputs and outputs, push-constant bytes and specialization constants the module declares.
 * Upstream answers it with SPIRV-Cross (Apache-2.0, C++), which a GPL-2.0-only game cannot hold. This file answers the same
 * question from the SPIR-V specification alone (Khronos, "SPIR-V Specification", sections 2.3 "Physical Layout" and 3 "Binary
 * Form"): one pass over the module's instructions, no SPIRV-Cross code read or copied. tools/psx_spirv_reflect_selftest.py
 * checks, on a developer's machine, that every prebuilt shader of the pinned Beetle gets the answer SPIRV-Cross gives.
 *
 * What the answer holds (the struct's own field names):
 *   - per descriptor set, a mask of bindings by kind: combined image samplers, separate images, separate samplers, storage
 *     images, input attachments, texel buffers, uniform buffers, storage buffers; which image bindings sample floats; and the
 *     stock sampler a binding's variable name asks for ("LinearClamp"...), four bits per binding;
 *   - a mask of the locations of the stage inputs and of the stage outputs (built-ins are not resources);
 *   - the declared size of the push-constant block; a mask of the specialization constant ids. */
#include "rhi_spirv_reflect.h"

#include <stdlib.h>
#include <string.h>

/* SPIR-V opcodes, decorations, storage classes and image dimensions used here (the specification's numbers). */
enum { OP_NAME = 5, OP_TYPE_BOOL = 20, OP_TYPE_INT = 21, OP_TYPE_FLOAT = 22, OP_TYPE_VECTOR = 23, OP_TYPE_MATRIX = 24,
       OP_TYPE_IMAGE = 25, OP_TYPE_SAMPLER = 26, OP_TYPE_SAMPLED_IMAGE = 27, OP_TYPE_ARRAY = 28, OP_TYPE_RUNTIME_ARRAY = 29,
       OP_TYPE_STRUCT = 30, OP_TYPE_POINTER = 32, OP_CONSTANT = 43, OP_SPEC_CONSTANT_TRUE = 48, OP_SPEC_CONSTANT_FALSE = 49,
       OP_SPEC_CONSTANT = 50, OP_VARIABLE = 59, OP_DECORATE = 71, OP_MEMBER_DECORATE = 72 };
enum { DEC_SPEC_ID = 1, DEC_BLOCK = 2, DEC_BUFFER_BLOCK = 3, DEC_ROW_MAJOR = 4, DEC_ARRAY_STRIDE = 6, DEC_MATRIX_STRIDE = 7,
       DEC_BUILT_IN = 11, DEC_LOCATION = 30, DEC_BINDING = 33, DEC_DESCRIPTOR_SET = 34, DEC_OFFSET = 35 };
enum { SC_UNIFORM_CONSTANT = 0, SC_INPUT = 1, SC_UNIFORM = 2, SC_OUTPUT = 3, SC_PUSH_CONSTANT = 9, SC_STORAGE_BUFFER = 12 };
enum { DIM_BUFFER = 5, DIM_SUBPASS_DATA = 6 };
enum { STOCK_SAMPLERS = 8 };

typedef struct {
    uint16_t op;                 /* the instruction that made this id (a type, a constant, a variable), 0: none */
    const uint32_t *words;       /* that instruction */
    uint16_t count;              /* its word count */
    const char *name;            /* OpName, or NULL */
    uint32_t set, binding, location, spec_id, array_stride;
    uint8_t has_spec_id, block, buffer_block, built_in, member_built_in;
} Id;

typedef struct { const uint32_t *data; size_t words; Id *ids; uint32_t bound; } Module;

static const Id *id_of(const Module *m, uint32_t id) { return id < m->bound ? &m->ids[id] : &m->ids[0]; }

/* The type behind arrays (an array of resources is one resource). */
static const Id *element_type(const Module *m, const Id *type) {
    while (type->op == OP_TYPE_ARRAY || type->op == OP_TYPE_RUNTIME_ARRAY) type = id_of(m, type->words[2]);
    return type;
}

static int stock_sampler(const char *name, unsigned *sampler) {
    static const char *const names[STOCK_SAMPLERS] = {"NearestClamp", "LinearClamp", "TrilinearClamp", "NearestWrap", "LinearWrap",
                                                      "TrilinearWrap", "NearestShadow", "LinearShadow"};
    if (!name) return 0;
    for (unsigned i = 0; i < STOCK_SAMPLERS; ++i)
        if (strstr(name, names[i])) { *sampler = i; return 1; }
    return 0;
}

/* The first name's sampler stays (upstream reports a mismatch and keeps the first one too). */
static void immutable_sampler(RhiSpirvDescriptorSetLayout *set, uint32_t binding, const char *name) {
    unsigned sampler;
    if (!stock_sampler(name, &sampler) || (set->immutable_sampler_mask & (1u << binding))) return;
    set->immutable_samplers |= (uint64_t)sampler << (4 * binding);
    set->immutable_sampler_mask |= 1u << binding;
}

static int samples_float(const Module *m, const Id *image) { return id_of(m, image->words[2])->op == OP_TYPE_FLOAT; }

/* Member decorations of a struct: looked up on demand (the push-constant block only). */
static int member_decoration(const Module *m, uint32_t type, uint32_t member, uint32_t decoration, uint32_t *value) {
    for (size_t at = 5; at < m->words;) {
        const uint32_t *w = m->data + at;
        const uint32_t count = w[0] >> 16;
        if (!count || at + count > m->words) break;
        if ((w[0] & 0xFFFF) == OP_MEMBER_DECORATE && count >= 4 && w[1] == type && w[2] == member && w[3] == decoration) {
            if (value) *value = count >= 5 ? w[4] : 0;
            return 1;
        }
        at += count;
    }
    return 0;
}

static uint32_t struct_size(const Module *m, uint32_t type);

/* The bytes a struct member declares: an array is its stride times its length, a matrix its stride times its columns (its rows
 * when row-major), a vector its components, a struct its own declared size. */
static uint32_t member_size(const Module *m, uint32_t owner, uint32_t member, uint32_t type_id) {
    const Id *type = id_of(m, type_id);
    switch (type->op) {
    case OP_TYPE_ARRAY: {
        const Id *length = id_of(m, type->words[3]);
        const uint32_t n = length->op == OP_CONSTANT && length->count >= 4 ? length->words[3] : 0;
        return type->array_stride * n;
    }
    case OP_TYPE_STRUCT: return struct_size(m, type_id);
    case OP_TYPE_MATRIX: {
        uint32_t stride = 0;
        const Id *column = id_of(m, type->words[2]);
        member_decoration(m, owner, member, DEC_MATRIX_STRIDE, &stride);
        return stride * (member_decoration(m, owner, member, DEC_ROW_MAJOR, NULL) ? column->words[3] : type->words[3]);
    }
    case OP_TYPE_VECTOR: return type->words[3] * member_size(m, owner, member, type->words[2]);
    case OP_TYPE_INT: case OP_TYPE_FLOAT: return type->words[2] / 8;
    case OP_TYPE_BOOL: return 4;
    default: return 0;
    }
}

/* The declared size of a struct: where its furthest member ends (offsets may be declared in any order). */
static uint32_t struct_size(const Module *m, uint32_t type_id) {
    const Id *type = id_of(m, type_id);
    uint32_t last = 0, last_offset = 0;
    if (type->op != OP_TYPE_STRUCT || type->count < 3) return 0;
    for (uint32_t i = 0; i + 2 < type->count; ++i) {
        uint32_t offset = 0;
        member_decoration(m, type_id, i, DEC_OFFSET, &offset);
        if (offset >= last_offset) { last_offset = offset; last = i; }
    }
    return last_offset + member_size(m, type_id, last, type->words[2 + last]);
}

void rhi_spirv_reflect(const uint32_t *data, size_t word_count, RhiSpirvResourceLayout *out) {
    Module m = {data, word_count, NULL, 0};
    memset(out, 0, sizeof(*out));
    if (!data || word_count < 5 || data[0] != 0x07230203u) return;
    m.bound = data[3];
    if (!m.bound || m.bound > (1u << 22) || !(m.ids = (Id *)calloc(m.bound, sizeof(Id)))) return;

    /* First pass: what each id is, its name and its decorations. */
    for (size_t at = 5; at < word_count;) {
        const uint32_t *w = data + at;
        const uint32_t count = w[0] >> 16, op = w[0] & 0xFFFF;
        uint32_t target = 0;
        if (!count || at + count > word_count) break;
        switch (op) {
        case OP_NAME: if (count >= 3 && w[1] < m.bound) m.ids[w[1]].name = (const char *)(w + 2); break;
        case OP_DECORATE:
            if (count >= 3 && w[1] < m.bound) {
                Id *id = &m.ids[w[1]];
                const uint32_t value = count >= 4 ? w[3] : 0;
                switch (w[2]) {
                case DEC_SPEC_ID: id->spec_id = value; id->has_spec_id = 1; break;
                case DEC_BLOCK: id->block = 1; break;
                case DEC_BUFFER_BLOCK: id->buffer_block = 1; break;
                case DEC_BUILT_IN: id->built_in = 1; break;
                case DEC_LOCATION: id->location = value; break;
                case DEC_BINDING: id->binding = value; break;
                case DEC_DESCRIPTOR_SET: id->set = value; break;
                case DEC_ARRAY_STRIDE: id->array_stride = value; break;
                default: break;
                }
            }
            break;
        case OP_MEMBER_DECORATE: if (count >= 4 && w[1] < m.bound && w[3] == DEC_BUILT_IN) m.ids[w[1]].member_built_in = 1; break;
        case OP_TYPE_BOOL: case OP_TYPE_INT: case OP_TYPE_FLOAT: case OP_TYPE_VECTOR: case OP_TYPE_MATRIX: case OP_TYPE_IMAGE:
        case OP_TYPE_SAMPLER: case OP_TYPE_SAMPLED_IMAGE: case OP_TYPE_ARRAY: case OP_TYPE_RUNTIME_ARRAY: case OP_TYPE_STRUCT:
        case OP_TYPE_POINTER: target = count >= 2 ? w[1] : 0; break;
        case OP_CONSTANT: case OP_SPEC_CONSTANT_TRUE: case OP_SPEC_CONSTANT_FALSE: case OP_SPEC_CONSTANT: case OP_VARIABLE:
            target = count >= 3 ? w[2] : 0;
            break;
        default: break;
        }
        if (target && target < m.bound) { m.ids[target].op = (uint16_t)op; m.ids[target].words = w; m.ids[target].count = (uint16_t)count; }
        at += count;
    }

    /* Second pass: the variables and the specialization constants, in the module's order. */
    for (uint32_t i = 1; i < m.bound; ++i) {
        const Id *id = &m.ids[i];
        if (id->has_spec_id && (id->op == OP_SPEC_CONSTANT || id->op == OP_SPEC_CONSTANT_TRUE || id->op == OP_SPEC_CONSTANT_FALSE)) {
            if (id->spec_id < RHI_SPIRV_NUM_SPEC_CONSTANTS) out->spec_constant_mask |= 1u << id->spec_id;
            continue;
        }
        if (id->op != OP_VARIABLE || id->count < 4) continue;
        const Id *pointer = id_of(&m, id->words[1]);
        if (pointer->op != OP_TYPE_POINTER) continue;
        const uint32_t storage = id->words[3];
        const uint32_t pointee = pointer->words[3];
        const Id *type = element_type(&m, id_of(&m, pointee));
        const uint32_t bit = id->binding < 32 ? 1u << id->binding : 0;
        RhiSpirvDescriptorSetLayout *set = id->set < RHI_SPIRV_NUM_DESCRIPTOR_SETS ? &out->sets[id->set] : NULL;
        if (storage == SC_INPUT || storage == SC_OUTPUT) {
            if (id->built_in || (type->op == OP_TYPE_STRUCT && type->member_built_in) || id->location >= 32) continue;
            if (storage == SC_INPUT) out->input_mask |= 1u << id->location; else out->output_mask |= 1u << id->location;
        } else if (storage == SC_PUSH_CONSTANT) {
            if (!out->push_constant_size) out->push_constant_size = struct_size(&m, (uint32_t)(type->words[1]));
        } else if (!set) {
            continue;
        } else if (storage == SC_STORAGE_BUFFER || (storage == SC_UNIFORM && type->op == OP_TYPE_STRUCT && type->buffer_block)) {
            set->storage_buffer_mask |= bit;
        } else if (storage == SC_UNIFORM && type->op == OP_TYPE_STRUCT) {
            set->uniform_buffer_mask |= bit;
        } else if (storage == SC_UNIFORM_CONSTANT && type->op == OP_TYPE_SAMPLED_IMAGE) {
            const Id *image = id_of(&m, type->words[2]);
            if (image->op != OP_TYPE_IMAGE) continue;
            if (image->words[3] == DIM_BUFFER) set->sampled_buffer_mask |= bit; else set->sampled_image_mask |= bit;
            if (samples_float(&m, image)) set->fp_mask |= bit;
            if (image->words[3] != DIM_BUFFER && id->binding < 16) immutable_sampler(set, id->binding, id->name);
        } else if (storage == SC_UNIFORM_CONSTANT && type->op == OP_TYPE_IMAGE) {
            const uint32_t dim = type->words[3], sampled = type->count >= 8 ? type->words[7] : 0;
            if (dim == DIM_SUBPASS_DATA) set->input_attachment_mask |= bit;
            else if (sampled == 2) set->storage_image_mask |= bit;
            else if (dim == DIM_BUFFER) set->sampled_buffer_mask |= bit;
            else set->separate_image_mask |= bit;
            if (samples_float(&m, type)) set->fp_mask |= bit;
        } else if (storage == SC_UNIFORM_CONSTANT && type->op == OP_TYPE_SAMPLER) {
            set->sampler_mask |= bit;
            if (id->binding < 16) immutable_sampler(set, id->binding, id->name);
        }
    }
    free(m.ids);
}
