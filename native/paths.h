#ifndef RETRO_RECOMP_PATHS_H
#define RETRO_RECOMP_PATHS_H
#include <wchar.h>
#include <stdio.h>
#define RETRO_PATH_CAP 32768
int retro_make_directories(wchar_t *path);
int retro_executable_directory(wchar_t *out);
/* Path resolution is read-only. Only file creation modes prepare directories. */
int retro_data_directory(wchar_t *out);
int retro_game_directory(wchar_t *out);
FILE *retro_game_file(const wchar_t *suffix, const wchar_t *mode);
void retro_game_file_reset(const wchar_t *suffix);
int retro_game_file_replace(const wchar_t *temporary, const wchar_t *destination);
#endif
