#ifndef SMSRECOMP_LEARNING_H
#define SMSRECOMP_LEARNING_H
#include <stdio.h>
#include <stdint.h>
FILE *smsrecomp_observations_read(void);
int smsrecomp_observe(uint16_t address, uint8_t b0, uint8_t b1, uint8_t b2, uint32_t hash);
int smsrecomp_observe_code(const uint8_t bytes[4]);
#endif
