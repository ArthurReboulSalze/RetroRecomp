/* The windows a headless run learns (`--learn FILE`): the four bytes at each address the interpreter ran, kept once each, in the
 * order they were first seen. MIT, Retro-Recomp.
 *
 * It has NO bound: a game that runs a lot of code from RAM (a loader that decompresses routines, a program that rewrites its own
 * interrupt handler) learns thousands of windows, and every window dropped here is code that runs on the interpreter again on the
 * next generation. The set is a growing array (the windows, in first-seen order, which is what the writers print) and an open-addressing
 * table of indexes (the duplicate test, constant time: the interpreter observes the windows of every step it runs).
 * Included by native/z80_chain_glue.inc; checked alone by native/z80_learned_set_checks.c (tools/z80_learned_set_selftest.py). */
#ifndef RR_Z80_LEARNED_SET_H
#define RR_Z80_LEARNED_SET_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    uint32_t *words;       /* the windows, first seen first */
    size_t count, capacity;
    uint32_t *table;       /* index + 1 into words, 0 for an empty slot; a power of two long */
    size_t table_size;
} RrLearnedSet;

static size_t rr_learned_slot(uint32_t word, size_t table_size)
{
    return (size_t)(((uint64_t)word * UINT64_C(11400714819323198485)) >> 32) & (table_size - 1);
}

static void rr_learned_grow_table(RrLearnedSet *set)
{
    size_t size = set->table_size ? set->table_size * 2 : 1024;
    uint32_t *table = (uint32_t *)calloc(size, sizeof *table);
    if (!table) { fprintf(stderr, "[learning] out of memory\n"); exit(1); }
    for (size_t i = 0; i < set->count; ++i) {
        size_t slot = rr_learned_slot(set->words[i], size);
        while (table[slot]) slot = (slot + 1) & (size - 1);
        table[slot] = (uint32_t)(i + 1);
    }
    free(set->table);
    set->table = table;
    set->table_size = size;
}

/* Keeps `word` unless it is there already; returns 1 when it is new. */
static int rr_learned_add(RrLearnedSet *set, uint32_t word)
{
    if (set->count * 2 >= set->table_size) rr_learned_grow_table(set);
    size_t slot = rr_learned_slot(word, set->table_size);
    while (set->table[slot]) {
        if (set->words[set->table[slot] - 1] == word) return 0;
        slot = (slot + 1) & (set->table_size - 1);
    }
    if (set->count == set->capacity) {
        size_t capacity = set->capacity ? set->capacity * 2 : 1024;
        uint32_t *words = (uint32_t *)realloc(set->words, capacity * sizeof *words);
        if (!words) { fprintf(stderr, "[learning] out of memory\n"); exit(1); }
        set->words = words;
        set->capacity = capacity;
    }
    set->words[set->count++] = word;
    set->table[slot] = (uint32_t)set->count;
    return 1;
}

#endif
