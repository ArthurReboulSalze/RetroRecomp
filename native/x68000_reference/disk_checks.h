/* Original Retro-Recomp private authored disk diagnostics, MIT. */
#ifndef RR_X68000_DISK_CHECKS_H
#define RR_X68000_DISK_CHECKS_H
/* Called only after normal gameplay reports, on the guest thread. Creates two
 * authored blank DIM images beside report_path; no supplied media are changed.
 * Returns all nine bits on success; JSON includes state_restored separately. */
unsigned rr_x68k_disk_checks(const char *report_path);
#endif
