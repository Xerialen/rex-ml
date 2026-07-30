/*
 * qwsim core — batched slot driver around the byte-identical mvdsv pmove.
 *
 * This file is NOT from mvdsv. It replicates the per-command player-movement
 * path of SV_RunCmd (sv_user.c:3777-3813 in vendor/mvdsv-src) around the
 * untouched PM_PlayerMove():
 *
 *   - pmove.origin/velocity/angles/waterjumptime seeded from slot state
 *     (offset is zero for live players: v->mins == player_mins)
 *   - cmd.angles[PITCH] clamped to [sv_minpitch, sv_maxpitch] = [-70, 80]
 *   - pmove.jump_msec = 0 (server always)
 *   - KTeams "broken ankle" hack: velocity[2] == -270 && jump pressed
 *     => jump_held forced true (sv_user.c:3786-3795)
 *   - physents = { world } only (static world; func_plat/doors are server
 *     entities outside pmove — see EXTRACTION-NOTES.md)
 *   - movevars per sv_user.c:3803-3810 with entgravity/maxspeed global
 *
 * Threading: every OpenMP worker owns thread-local pmove state
 * (QWSIM-EDIT-1..8), slots are copied in/out around PM_PlayerMove.
 */
#define SERVERONLY 1
#include "qwsvdef.h"
#include "qwsim_api.h"
#include <setjmp.h>
#ifdef _OPENMP
#include <omp.h>
#endif

extern __thread jmp_buf qwsim_errjmp;
extern __thread int     qwsim_errjmp_armed;
extern __thread char    qwsim_errmsg[512];

#define SV_MINPITCH (-70.0f)
#define SV_MAXPITCH (80.0f)

typedef struct {
	vec3_t origin;
	vec3_t velocity;
	vec3_t angles;        /* last cmd angles, for get_state */
	float  waterjumptime;
	qbool  jump_held;
	qbool  onground;
	int    waterlevel;
} qwsim_slot_t;

static cmodel_t     *qwsim_world = NULL;
static unsigned      qwsim_checksum, qwsim_checksum2;
static qwsim_slot_t *qwsim_slots = NULL;
static int           qwsim_nslots = 0;
static int           qwsim_threads = 0;   /* 0 = library default */

/* ------------------------------------------------------------------ */

void qwsim_get_default_movevars (qwsim_movevars_t *mv)
{
	/* mvdsv defaults (sv_phys.c:46-66) == the values locked in
	 * ~/mlx/qwserver/serverdir/rtx/dragonbot_rtx_27500.cfg.
	 * entgravity = 1.0 (sv_phys.c:1133 / sv_user.c:3803 default). */
	mv->gravity = 800;  mv->stopspeed = 100; mv->maxspeed = 320;
	mv->spectatormaxspeed = 500;
	mv->accelerate = 10; mv->airaccelerate = 10; mv->wateraccelerate = 10;
	mv->friction = 4;    mv->waterfriction = 4;  mv->entgravity = 1.0;
	mv->bunnyspeedcap = 0; mv->ktjump = 1;
	mv->slidefix = 0; mv->airstep = 0; mv->pground = 0; mv->rampjump = 0;
}

void qwsim_set_movevars (const qwsim_movevars_t *mv)
{
	movevars.gravity           = (float)mv->gravity;
	movevars.stopspeed         = (float)mv->stopspeed;
	movevars.maxspeed          = (float)mv->maxspeed;
	movevars.spectatormaxspeed = (float)mv->spectatormaxspeed;
	movevars.accelerate        = (float)mv->accelerate;
	movevars.airaccelerate     = (float)mv->airaccelerate;
	movevars.wateraccelerate   = (float)mv->wateraccelerate;
	movevars.friction          = (float)mv->friction;
	movevars.waterfriction     = (float)mv->waterfriction;
	movevars.entgravity        = (float)mv->entgravity;
	movevars.bunnyspeedcap     = (float)mv->bunnyspeedcap;
	movevars.ktjump            = (float)mv->ktjump;
	movevars.slidefix          = mv->slidefix ? true : false;
	movevars.airstep           = mv->airstep ? true : false;
	movevars.pground           = mv->pground ? true : false;
	movevars.rampjump          = mv->rampjump;
}

void qwsim_get_movevars (qwsim_movevars_t *mv)
{
	mv->gravity = movevars.gravity; mv->stopspeed = movevars.stopspeed;
	mv->maxspeed = movevars.maxspeed;
	mv->spectatormaxspeed = movevars.spectatormaxspeed;
	mv->accelerate = movevars.accelerate;
	mv->airaccelerate = movevars.airaccelerate;
	mv->wateraccelerate = movevars.wateraccelerate;
	mv->friction = movevars.friction; mv->waterfriction = movevars.waterfriction;
	mv->entgravity = movevars.entgravity;
	mv->bunnyspeedcap = movevars.bunnyspeedcap; mv->ktjump = movevars.ktjump;
	mv->slidefix = movevars.slidefix; mv->airstep = movevars.airstep;
	mv->pground = movevars.pground; mv->rampjump = movevars.rampjump;
}

/* ------------------------------------------------------------------ */

int qwsim_load_bsp (const char *path, char *err, int errlen)
{
	qwsim_movevars_t mv;

	qwsim_unload_bsp ();

	qwsim_errjmp_armed = 1;
	if (setjmp (qwsim_errjmp)) {
		qwsim_errjmp_armed = 0;
		if (err) { strncpy (err, qwsim_errmsg, errlen - 1); err[errlen - 1] = 0; }
		qwsim_world = NULL;
		return -1;
	}

	CM_Init ();
	qwsim_world = CM_LoadMap ((char *)path, false, &qwsim_checksum, &qwsim_checksum2);
	qwsim_errjmp_armed = 0;

	if (!qwsim_world) {
		if (err) { strncpy (err, "CM_LoadMap returned NULL", errlen - 1); err[errlen - 1] = 0; }
		return -1;
	}

	qwsim_get_default_movevars (&mv);
	qwsim_set_movevars (&mv);
	return 0;
}

void qwsim_unload_bsp (void)
{
	if (qwsim_world) {
		CM_InvalidateMap ();
		QWSIM_HunkReset ();
		qwsim_world = NULL;
	}
}

int qwsim_map_loaded (void) { return qwsim_world != NULL; }
unsigned qwsim_map_checksum2 (void) { return qwsim_checksum2; }

int qwsim_alloc_slots (int n)
{
	free (qwsim_slots);
	qwsim_slots = (qwsim_slot_t *)calloc ((size_t)n, sizeof(qwsim_slot_t));
	qwsim_nslots = qwsim_slots ? n : 0;
	return qwsim_nslots;
}

int qwsim_num_slots (void) { return qwsim_nslots; }

void qwsim_set_num_threads (int n) { qwsim_threads = n; }
int  qwsim_get_num_threads (void)
{
#ifdef _OPENMP
	return qwsim_threads > 0 ? qwsim_threads : omp_get_max_threads ();
#else
	return 1;
#endif
}

void qwsim_reset_slots (int count, const int32_t *slot_ids,
                        const float *pos, const float *vel,
                        const float *angles,
                        const uint8_t *onground, const uint8_t *jump_held,
                        const float *waterjumptime)
{
	int i, k;
	for (i = 0; i < count; i++) {
		qwsim_slot_t *s;
		int id = slot_ids ? slot_ids[i] : i;
		if (id < 0 || id >= qwsim_nslots)
			continue;
		s = &qwsim_slots[id];
		for (k = 0; k < 3; k++) {
			s->origin[k]   = pos[i * 3 + k];
			s->velocity[k] = vel[i * 3 + k];
			s->angles[k]   = angles ? angles[i * 3 + k] : 0;
		}
		s->onground      = (onground && onground[i]) ? true : false;
		s->jump_held     = (jump_held && jump_held[i]) ? true : false;
		s->waterjumptime = waterjumptime ? waterjumptime[i] : 0;
		s->waterlevel    = 0;
	}
}

/* ------------------------------------------------------------------ */

static void qwsim_step_one (qwsim_slot_t *s,
                            const float *ang, int16_t fm, int16_t sm,
                            int16_t um, uint8_t buttons, uint8_t msec,
                            int32_t *blocked_out)
{
	int blocked;

	memset (&pmove.cmd, 0, sizeof(pmove.cmd));

	VectorCopy (s->origin, pmove.origin);
	VectorCopy (s->velocity, pmove.velocity);
	pmove.angles[0] = ang[0]; pmove.angles[1] = ang[1]; pmove.angles[2] = ang[2];
	pmove.waterjumptime = s->waterjumptime;

	pmove.cmd.msec = msec;
	/* sv_user.c:3723 — clamp view pitch before pmove */
	pmove.cmd.angles[PITCH] = bound (SV_MINPITCH, ang[PITCH], SV_MAXPITCH);
	pmove.cmd.angles[YAW]   = ang[YAW];
	pmove.cmd.angles[ROLL]  = ang[ROLL];
	pmove.cmd.forwardmove = fm;
	pmove.cmd.sidemove    = sm;
	pmove.cmd.upmove      = um;
	pmove.cmd.buttons     = buttons;
	pmove.cmd.impulse     = 0;

	pmove.pm_type   = PM_NORMAL;
	pmove.onground  = s->onground;
	pmove.jump_held = s->jump_held;
	pmove.jump_msec = 0;

	/* KTeams "broken ankle" hack, sv_user.c:3786-3795 */
	if (pmove.velocity[2] == -270 && (pmove.cmd.buttons & BUTTON_JUMP))
		pmove.jump_held = true;

	pmove.numphysent = 1;
	pmove.physents[0].model = qwsim_world;
	VectorClear (pmove.physents[0].origin);
	pmove.physents[0].info = 0;

	blocked = PM_PlayerMove ();

	VectorCopy (pmove.origin, s->origin);
	VectorCopy (pmove.velocity, s->velocity);
	VectorCopy (pmove.angles, s->angles);
	s->waterjumptime = pmove.waterjumptime;
	s->jump_held     = pmove.jump_held;
	s->onground      = pmove.onground;
	s->waterlevel    = pmove.waterlevel;
	if (blocked_out)
		*blocked_out = blocked;
}

void qwsim_step_batch (int count, const int32_t *slot_ids,
                       const float *angles,
                       const int16_t *forwardmove, const int16_t *sidemove,
                       const int16_t *upmove, const uint8_t *buttons,
                       const uint8_t *msec,
                       float *out_pos, float *out_vel,
                       uint8_t *out_onground, uint8_t *out_waterlevel,
                       uint8_t *out_jump_held, int32_t *out_blocked)
{
	int i;
	if (!qwsim_world || !qwsim_slots)
		return;

#ifdef _OPENMP
	if (qwsim_threads > 0)
		omp_set_num_threads (qwsim_threads);
#endif

#pragma omp parallel if(count > 16)
	{
		CM_Init ();   /* per-thread box hull (QWSIM-EDIT-6..8); world untouched */
#pragma omp for schedule(static)
		for (i = 0; i < count; i++) {
			int id = slot_ids ? slot_ids[i] : i;
			qwsim_slot_t *s;
			int32_t blocked = 0;
			if (id < 0 || id >= qwsim_nslots)
				continue;
			s = &qwsim_slots[id];
			qwsim_step_one (s, angles + i * 3,
			                forwardmove[i], sidemove[i], upmove[i],
			                buttons[i], msec[i], &blocked);
			if (out_pos) {
				out_pos[i * 3 + 0] = s->origin[0];
				out_pos[i * 3 + 1] = s->origin[1];
				out_pos[i * 3 + 2] = s->origin[2];
			}
			if (out_vel) {
				out_vel[i * 3 + 0] = s->velocity[0];
				out_vel[i * 3 + 1] = s->velocity[1];
				out_vel[i * 3 + 2] = s->velocity[2];
			}
			if (out_onground)   out_onground[i]   = (uint8_t)(s->onground != 0);
			if (out_waterlevel) out_waterlevel[i] = (uint8_t)s->waterlevel;
			if (out_jump_held)  out_jump_held[i]  = (uint8_t)(s->jump_held != 0);
			if (out_blocked)    out_blocked[i]    = blocked;
		}
	}
}

void qwsim_get_state (int count, const int32_t *slot_ids,
                      float *pos, float *vel, float *angles,
                      uint8_t *onground, uint8_t *waterlevel,
                      uint8_t *jump_held, float *waterjumptime)
{
	int i, k;
	for (i = 0; i < count; i++) {
		int id = slot_ids ? slot_ids[i] : i;
		qwsim_slot_t *s;
		if (id < 0 || id >= qwsim_nslots)
			continue;
		s = &qwsim_slots[id];
		for (k = 0; k < 3; k++) {
			if (pos)    pos[i * 3 + k]    = s->origin[k];
			if (vel)    vel[i * 3 + k]    = s->velocity[k];
			if (angles) angles[i * 3 + k] = s->angles[k];
		}
		if (onground)      onground[i]      = (uint8_t)(s->onground != 0);
		if (waterlevel)    waterlevel[i]    = (uint8_t)s->waterlevel;
		if (jump_held)     jump_held[i]     = (uint8_t)(s->jump_held != 0);
		if (waterjumptime) waterjumptime[i] = s->waterjumptime;
	}
}

/* ------------------------------------------------------------------ */

void qwsim_trace_rays (int count, const float *origins, const float *dirs,
                       float max_dist, float *fractions, float *normals,
                       uint8_t *startsolid)
{
	hull_t *hull;
	int i;

	if (!qwsim_world)
		return;
	hull = &qwsim_world->hulls[0];   /* point hull — perception rays */

#ifdef _OPENMP
	if (qwsim_threads > 0)
		omp_set_num_threads (qwsim_threads);
#endif

#pragma omp parallel for schedule(static) if(count > 64)
	for (i = 0; i < count; i++) {
		vec3_t start, end;
		trace_t tr;
		start[0] = origins[i * 3 + 0];
		start[1] = origins[i * 3 + 1];
		start[2] = origins[i * 3 + 2];
		end[0] = start[0] + dirs[i * 3 + 0] * max_dist;
		end[1] = start[1] + dirs[i * 3 + 1] * max_dist;
		end[2] = start[2] + dirs[i * 3 + 2] * max_dist;

		tr = CM_HullTrace (hull, start, end);

		if (fractions)
			fractions[i] = tr.fraction;
		if (normals) {
			normals[i * 3 + 0] = tr.plane.normal[0];
			normals[i * 3 + 1] = tr.plane.normal[1];
			normals[i * 3 + 2] = tr.plane.normal[2];
		}
		if (startsolid)
			startsolid[i] = (uint8_t)(tr.startsolid != 0);
	}
}

void qwsim_point_contents (int count, const float *points, int32_t *contents)
{
	hull_t *hull;
	int i;
	if (!qwsim_world)
		return;
	hull = &qwsim_world->hulls[0];
#pragma omp parallel for schedule(static) if(count > 256)
	for (i = 0; i < count; i++) {
		vec3_t p;
		p[0] = points[i * 3 + 0];
		p[1] = points[i * 3 + 1];
		p[2] = points[i * 3 + 2];
		contents[i] = CM_HullPointContents (hull, hull->firstclipnode, p);
	}
}
