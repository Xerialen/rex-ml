/*
 * QWSIM SHIM IMPLEMENTATION — this file is NOT from mvdsv.
 *
 * Provides the server-infrastructure functions cmodel.c/mathlib.c call:
 * hunk allocator (malloc-backed), stdio VFS, cvar stubs, error handling.
 * None of this code is on the physics path; PM_* / CM_HullTrace /
 * CM_HullPointContents run entirely inside the byte-identical copies.
 */
#define SERVERONLY 1
#include "qwsvdef.h"
#include <setjmp.h>

/* ---------- error handling --------------------------------------------- */
/* When armed (during API calls from Python) Sys_Error longjmps back to the
 * wrapper instead of killing the interpreter. */
__thread jmp_buf qwsim_errjmp;
__thread int     qwsim_errjmp_armed = 0;
__thread char    qwsim_errmsg[512];

void Sys_Error (const char *error, ...)
{
	va_list argptr;
	va_start (argptr, error);
	vsnprintf (qwsim_errmsg, sizeof(qwsim_errmsg), error, argptr);
	va_end (argptr);
	if (qwsim_errjmp_armed)
		longjmp (qwsim_errjmp, 1);
	fprintf (stderr, "qwsim fatal (unarmed): %s\n", qwsim_errmsg);
	abort ();
}

void Con_Printf (const char *fmt, ...)
{
	va_list argptr;
	va_start (argptr, fmt);
	vfprintf (stderr, fmt, argptr);
	va_end (argptr);
}

/* ---------- cvars (only the three cmodel.c touches) --------------------- */
cvar_t sv_bspversion  = { "sv_bspversion", "1", 0, 1 };
cvar_t sv_halflifebsp = { "sv_halflifebsp", "0", 0, 0 };
cvar_t pm_rampjump    = { "pm_rampjump", "0", 0, 0 };

void Cvar_SetValue (cvar_t *var, float value) { var->value = value; }
void Cvar_SetROM (cvar_t *var, const char *value) { var->string = value; var->value = (float)atof(value); }

/* ---------- hunk allocator --------------------------------------------- */
/* mvdsv semantics used by cmodel.c:
 *  - Hunk_AllocName: permanent, zero-filled, lives until map unload
 *  - Hunk_TempAlloc: frees all previous temp blocks, returns a fresh one
 *  - Hunk_TempAllocMore: additional temp block, previous blocks stay valid
 *  - Hunk_TempFlush: frees all temp blocks
 *  - Hunk_LowMark / Hunk_FreeToLowMark: rollback of permanent allocs
 * Contiguity of the real hunk is never relied upon by cmodel.c (every lump
 * is used through its own returned pointer), so independent mallocs match.
 */
#define QWSIM_MAX_ALLOCS 4096
static void *perm_allocs[QWSIM_MAX_ALLOCS]; static int perm_count = 0;
static void *temp_allocs[QWSIM_MAX_ALLOCS]; static int temp_count = 0;

void *Hunk_AllocName (int size, const char *name)
{
	void *p;
	(void)name;
	if (perm_count >= QWSIM_MAX_ALLOCS)
		Sys_Error ("qwsim hunk: too many permanent allocations");
	p = calloc (1, (size_t)size > 0 ? (size_t)size : 1);
	if (!p)
		Sys_Error ("qwsim hunk: out of memory (%d bytes)", size);
	perm_allocs[perm_count++] = p;
	return p;
}

int Hunk_LowMark (void) { return perm_count; }

void Hunk_FreeToLowMark (int mark)
{
	while (perm_count > mark)
		free (perm_allocs[--perm_count]);
}

void Hunk_TempFlush (void)
{
	while (temp_count > 0)
		free (temp_allocs[--temp_count]);
}

void *Hunk_TempAlloc (int size)
{
	Hunk_TempFlush ();
	return Hunk_TempAllocMore (size);
}

void *Hunk_TempAllocMore (int size)
{
	void *p;
	if (temp_count >= QWSIM_MAX_ALLOCS)
		Sys_Error ("qwsim hunk: too many temp allocations");
	p = calloc (1, (size_t)size > 0 ? (size_t)size : 1);
	if (!p)
		Sys_Error ("qwsim hunk: out of memory (%d bytes)", size);
	temp_allocs[temp_count++] = p;
	return p;
}

void QWSIM_HunkReset (void)
{
	Hunk_TempFlush ();
	Hunk_FreeToLowMark (0);
}

/* ---------- stdio VFS --------------------------------------------------- */
vfsfile_t *FS_OpenVFS (const char *filename, const char *mode, relativeto_t relativeto)
{
	FILE *f;
	vfsfile_t *vf;
	(void)relativeto;
	f = fopen (filename, mode);
	if (!f)
		return NULL;
	vf = (vfsfile_t *)malloc (sizeof(vfsfile_t));
	vf->f = f;
	return vf;
}

void VFS_CLOSE (vfsfile_t *vf)
{
	if (vf) {
		fclose (vf->f);
		free (vf);
	}
}

unsigned long VFS_GETLEN (vfsfile_t *vf)
{
	long cur = ftell (vf->f), len;
	fseek (vf->f, 0, SEEK_END);
	len = ftell (vf->f);
	fseek (vf->f, cur, SEEK_SET);
	return (unsigned long)len;
}

int VFS_SEEK (vfsfile_t *vf, unsigned long pos, int whence)
{
	return fseek (vf->f, (long)pos, whence);
}

int VFS_READ (vfsfile_t *vf, void *buffer, int bytestoread, void *err)
{
	(void)err;
	return (int)fread (buffer, 1, (size_t)bytestoread, vf->f);
}

/* .qpn external physics-normal override files: not used by the sim
 * (dm3.bsp / 100m.bsp carry no BSPX MVDSV_PHYSICSNORMALS lump either, so
 * physics normals fall back to the clipnode planes exactly like a stock
 * mvdsv install). */
byte *FS_LoadHunkFile (char *path, int *len)
{
	(void)path;
	if (len) *len = 0;
	return NULL;
}

/* Same semantics as mvdsv fs.c COM_FileBase: strip path and extension. */
void COM_FileBase (const char *in, char *out)
{
	const char *start, *end;
	int  length;

	end = in + strlen (in);
	start = in;

	{
		const char *p;
		for (p = in; *p; p++)
			if (*p == '/' || *p == '\\')
				start = p + 1;
	}
	{
		const char *p;
		for (p = end - 1; p > start; p--)
			if (*p == '.') { end = p; break; }
	}

	length = (int)(end - start);
	if (length < 1) {
		strcpy (out, "?model?");
		return;
	}
	if (length > 31)
		length = 31;
	memcpy (out, start, length);
	out[length] = 0;
}
