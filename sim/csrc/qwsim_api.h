/*
 * qwsim public C API — consumed by the pybind11 module.
 * Plain C types only; no engine headers leak through.
 */
#ifndef QWSIM_API_H
#define QWSIM_API_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
	double gravity, stopspeed, maxspeed, spectatormaxspeed;
	double accelerate, airaccelerate, wateraccelerate;
	double friction, waterfriction, entgravity;
	double bunnyspeedcap, ktjump;
	int    slidefix, airstep, pground, rampjump;
} qwsim_movevars_t;

/* returns 0 on success; on failure fills err (len errlen) */
int  qwsim_load_bsp (const char *path, char *err, int errlen);
void qwsim_unload_bsp (void);
int  qwsim_map_loaded (void);
unsigned qwsim_map_checksum2 (void);

void qwsim_get_default_movevars (qwsim_movevars_t *mv); /* mvdsv defaults */
void qwsim_set_movevars (const qwsim_movevars_t *mv);
void qwsim_get_movevars (qwsim_movevars_t *mv);

int  qwsim_alloc_slots (int n);   /* (re)allocate slot array, returns n */
int  qwsim_num_slots (void);

/* Reset a subset of slots. Arrays indexed 0..count-1; slot_ids selects slots.
 * angles may be NULL (zeroed). onground/jump_held/waterlevel seed the state
 * that SV_RunCmd would carry over from the previous server frame. */
void qwsim_reset_slots (int count, const int32_t *slot_ids,
                        const float *pos /* count*3 */,
                        const float *vel /* count*3 */,
                        const float *angles /* count*3 or NULL */,
                        const uint8_t *onground, const uint8_t *jump_held,
                        const float *waterjumptime /* or NULL */);

/* One server tick for every listed slot (parallel over slots, GIL-free).
 * Inputs are per-slot usercmd fields; angles in degrees (pitch,yaw,roll).
 * Outputs may be NULL if not wanted. Replicates the SV_RunCmd player path:
 * pitch clamp [sv_minpitch,sv_maxpitch] = [-70,80], jump_msec=0, the
 * "broken ankle" jump_held hack, physents = { world }. */
void qwsim_step_batch (int count, const int32_t *slot_ids,
                       const float *angles /* count*3 */,
                       const int16_t *forwardmove, const int16_t *sidemove,
                       const int16_t *upmove, const uint8_t *buttons,
                       const uint8_t *msec,
                       float *out_pos, float *out_vel,
                       uint8_t *out_onground, uint8_t *out_waterlevel,
                       uint8_t *out_jump_held, int32_t *out_blocked);

void qwsim_get_state (int count, const int32_t *slot_ids,
                      float *pos, float *vel, float *angles,
                      uint8_t *onground, uint8_t *waterlevel,
                      uint8_t *jump_held, float *waterjumptime);

/* Batched point-ray trace against the world hull 0 (perception rays).
 * dirs need not be normalised beyond caller convention; endpoints are
 * origin + dir*max_dist. Outputs: fraction in [0,1], impact normal
 * (zero if no hit), solid flag (start in solid). */
void qwsim_trace_rays (int count, const float *origins, const float *dirs,
                       float max_dist, float *fractions, float *normals,
                       uint8_t *startsolid);

/* Point contents at count points (CONTENTS_* negatives). */
void qwsim_point_contents (int count, const float *points, int32_t *contents);

void qwsim_set_num_threads (int n);
int  qwsim_get_num_threads (void);

#ifdef __cplusplus
}
#endif

#endif
