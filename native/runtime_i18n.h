/* Stable language IDs for the converter and all generated game hosts. */
#ifndef RR_RUNTIME_I18N_H
#define RR_RUNTIME_I18N_H
#include <wchar.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { RR_LANGUAGE_COUNT = 8 };
int rr_language_from_code(const char *code);
int rr_language_from_wide(const wchar_t *code);
const char *rr_language_code(int language);
const wchar_t *rr_language_wide(int language);
const char *rr_language_name(int language);
int rr_language_next(int language);
void rr_language_set(int language);
int rr_language_get(void);
const char *rr_translate(int language, const char *english, const char *french);
const char *rr_tr(const char *english);
#ifdef __cplusplus
}
#endif
#endif
