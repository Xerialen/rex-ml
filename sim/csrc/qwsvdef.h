/*
 * QWSIM SHIM HEADER — this file is NOT from mvdsv.
 *
 * pmove.c / pmovetst.c / cmodel.c / mathlib.c are byte-identical copies of
 * vendor/mvdsv-src/src (except the documented QWSIM-EDIT thread-locality
 * lines, see sim/EXTRACTION-NOTES.md).  With SERVERONLY defined those files
 * include exactly one header: "qwsvdef.h".  This shim reproduces the minimal
 * subset of the original qwsvdef.h include-chain (bothdefs.h, mathlib.h,
 * zone.h, cvar.h, common.h, fs.h, vfs.h, cmodel.h, pmove.h, protocol.h)
 * that the four physics translation units actually consume.
 *
 * Every type/macro here mirrors the mvdsv definition it replaces; the
 * provenance of each is listed in sim/EXTRACTION-NOTES.md.
 */
#ifndef __QWSVDEF_H__
#define __QWSVDEF_H__

#include <time.h>
#include <math.h>
#include <string.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>
#include <assert.h>
#include <limits.h>

/* ---- bothdefs.h subset ------------------------------------------------ */
typedef unsigned char byte;
#ifdef __cplusplus
typedef int qbool;
#else
typedef enum qbool_e { false, true } qbool;   /* mvdsv bothdefs.h:163 */
#endif

#ifndef max
#define max(a,b) ((a) > (b) ? (a) : (b))
#endif
#ifndef min
#define min(a,b) ((a) < (b) ? (a) : (b))
#endif
#define bound(a,b,c) ((a) >= (c) ? (a) : (b) < (a) ? (a) : (b) > (c) ? (c) : (b))

#define MAX_QPATH   64
#define MAX_OSPATH  128

/* x86-64 is little-endian: identity swaps (mvdsv bothdefs.h:206-208) */
#define LittleShort(x)  (x)
#define LittleLong(x)   (x)
#define LittleFloat(x)  (x)

#ifndef __GLIBC_PREREQ
size_t strlcpy(char *dst, const char *src, size_t siz);
#endif

/* ---- mathlib ---------------------------------------------------------- */
#include "mathlib.h"

/* ---- cvar.h subset ---------------------------------------------------- */
typedef struct cvar_s {
	const char  *name;
	const char  *string;
	int         flags;
	float       value;
} cvar_t;

#define CVAR_SERVERINFO 0   /* flags unused in the sim */
#define CVAR_ROM        0

void Cvar_SetValue (cvar_t *var, float value);
void Cvar_SetROM (cvar_t *var, const char *value);

/* ---- zone.h subset ---------------------------------------------------- */
void *Hunk_AllocName (int size, const char *name);
int   Hunk_LowMark (void);
void  Hunk_FreeToLowMark (int mark);
void  Hunk_TempFlush (void);
void *Hunk_TempAlloc (int size);
void *Hunk_TempAllocMore (int size);
void  QWSIM_HunkReset (void);   /* qwsim addition: free everything (map unload) */

/* ---- vfs.h / fs.h subset (stdio-backed) ------------------------------- */
typedef struct vfsfile_s { FILE *f; } vfsfile_t;
typedef int relativeto_t;
#define FS_GAME 0

vfsfile_t     *FS_OpenVFS (const char *filename, const char *mode, relativeto_t relativeto);
void           VFS_CLOSE (vfsfile_t *vf);
unsigned long  VFS_GETLEN (vfsfile_t *vf);
int            VFS_SEEK (vfsfile_t *vf, unsigned long pos, int whence);
int            VFS_READ (vfsfile_t *vf, void *buffer, int bytestoread, void *err);
byte          *FS_LoadHunkFile (char *path, int *len);
void           COM_FileBase (const char *in, char *out);

/* ---- common.h subset -------------------------------------------------- */
unsigned Com_BlockChecksum (void *buffer, int length);   /* md4.c */

/* ---- console / sys ---------------------------------------------------- */
void Con_Printf (const char *fmt, ...);
void Sys_Error (const char *error, ...);
#define Host_Error Sys_Error
#define SV_Error   Sys_Error

/* ---- protocol.h subset (QW-Group/qwprot src/protocol.h) --------------- */
typedef struct usercmd_s {
	byte    msec;
	vec3_t  angles;
	short   forwardmove;
	short   sidemove;
	short   upmove;
	byte    buttons;
	byte    impulse;
} usercmd_t;

#define BUTTON_ATTACK  (1 << 0)
#define BUTTON_JUMP    (1 << 1)
#define BUTTON_USE     (1 << 2)

/* ---- collision + player movement -------------------------------------- */
#include "cmodel.h"
#include "pmove.h"

#endif /* !__QWSVDEF_H__ */
