/* The shared presentation host accesses the initialized Neo Geo machine. */
#ifndef RR_NEOGEO_HOST_H
#define RR_NEOGEO_HOST_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
uint32_t *rr_ng_visible_pixels(void);
const int16_t *rr_ng_pcm(size_t *count);
void rr_ng_consume_pcm(void);
void rr_ng_audio_queue_probe(int playing,unsigned bytes,unsigned rate,unsigned period);
void rr_ng_host_timing(double seconds);
bool rr_ng_performance_enabled(void);
void rr_ng_host_cost(double busy_ms,double present_ms);
void rr_ng_host_frame(uint16_t p1,uint16_t p2);
uint32_t rr_ng_frame_index(void);
void rr_ng_restore_frame(uint32_t frame);
unsigned rr_ng_frame_limit(void);
bool rr_ng_enhanced(void);
void rr_ng_set_enhanced(bool enabled);
void rr_ng_reset_machine(void);
void rr_ng_ui_test_tick(void *window,void *renderer);
void rr_ng_ui_test_present(void *renderer);
void rr_ng_ui_snapshot(FILE *file,const char *label,void *window);
void rr_ng_test_json(FILE *file,const char *text);
bool rr_ng_core_state_valid(const uint8_t *data,size_t size);
size_t rr_ng_cpu_extra_save(uint8_t *data,size_t capacity);
bool rr_ng_cpu_extra_restore(const uint8_t *data,size_t size);
size_t rr_ng_ym_extra_save(uint8_t *data,size_t capacity);
bool rr_ng_ym_extra_restore(const uint8_t *data,size_t size);
#endif
