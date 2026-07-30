#!/usr/bin/env python3
"""Render every rex-drills evidence envelope in a directory into one self-contained HTML page.

Same CLI shape as the lab's dashboard builder:
    python3 dashboard/build_dashboard.py --evidence-dir evidence --output dashboard.html

Stdlib only, no network, no external assets — the page must open from a file:// URL on a machine
with nothing installed.
"""

import argparse
import glob
import html
import json
import os

# Human DM3 calibration from the step 1 corpus, for context on the speed numbers. These are
# measurements, not targets: a drill that runs slower than a human is not automatically a failure.
HUMAN_GROUND_MEDIAN = 313.0
HUMAN_AIR_PEAK = 1746.0

CSS = """
:root{--bg:#fbfbfd;--fg:#16171a;--mut:#63666e;--card:#fff;--line:#e3e4e8;
      --ok:#12793f;--okbg:#e8f6ed;--bad:#b0201c;--badbg:#fdeceb;--warn:#8a5a00;--warnbg:#fdf3e0;
      --accent:#2b5cd9}
@media (prefers-color-scheme:dark){:root{--bg:#101114;--fg:#e9eaee;--mut:#9a9ea8;--card:#181a1f;
      --line:#2a2d34;--ok:#57d98a;--okbg:#122b1c;--bad:#ff7b72;--badbg:#2e1514;--warn:#e0b25c;
      --warnbg:#2b2113;--accent:#7aa2f7}}
:root[data-theme=dark]{--bg:#101114;--fg:#e9eaee;--mut:#9a9ea8;--card:#181a1f;--line:#2a2d34;
      --ok:#57d98a;--okbg:#122b1c;--bad:#ff7b72;--badbg:#2e1514;--warn:#e0b25c;--warnbg:#2b2113;
      --accent:#7aa2f7}
:root[data-theme=light]{--bg:#fbfbfd;--fg:#16171a;--mut:#63666e;--card:#fff;--line:#e3e4e8;
      --ok:#12793f;--okbg:#e8f6ed;--bad:#b0201c;--badbg:#fdeceb;--warn:#8a5a00;--warnbg:#fdf3e0;
      --accent:#2b5cd9}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:19px;margin:34px 0 12px;letter-spacing:-.01em}
h3{font-size:14px;margin:20px 0 8px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
.sub{color:var(--mut);margin:0 0 22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 20px;
  margin:0 0 16px}
.banner{border-left:3px solid var(--warn);background:var(--warnbg);color:var(--fg)}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;
  letter-spacing:.02em}
.pass{background:var(--okbg);color:var(--ok)}
.fail{background:var(--badbg);color:var(--bad)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:6px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px}
.kpi .n{font-size:23px;font-weight:650;letter-spacing:-.02em}
.kpi .l{font-size:11.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);
  position:sticky;top:0;background:var(--card)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr.bad td{background:var(--badbg)}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}
.dl{display:grid;grid-template-columns:auto 1fr;gap:4px 16px;font-size:13.5px}
.dl dt{color:var(--mut)}
.dl dd{margin:0}
.bar{height:7px;border-radius:4px;background:var(--line);overflow:hidden;min-width:70px}
.bar>i{display:block;height:100%;background:var(--accent)}
.note{color:var(--mut);font-size:13px;margin:8px 0 0}
"""


def esc(x):
    return html.escape(str(x))


def kpi(n, label):
    return f'<div class="kpi"><div class="n">{esc(n)}</div><div class="l">{esc(label)}</div></div>'


def pill(ok, text=None):
    cls = "pass" if ok else "fail"
    return f'<span class="pill {cls}">{esc(text or ("pass" if ok else "fail"))}</span>'


def fmt(v, nd=1):
    if v is None:
        return "—"
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return str(v)
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return esc(v)


def build_section(env, src=""):
    tier = env.get("tier", "?")
    res = env.get("result", {})
    ok = env.get("status") == "passed"
    # Name the run in the heading: several envelopes can share a tier (a smoke run and a full one),
    # and two identically titled sections are indistinguishable once scrolled.
    run = os.path.basename(src).removesuffix(".json")
    out = [
        f'<h2>{esc(tier)} — {esc(env.get("kind",""))} '
        f'<span style="color:var(--mut);font-weight:400">{esc(run)}</span> '
        f'{pill(ok, env.get("status"))}</h2>'
    ]

    if tier == "T0":
        out.append(
            '<div class="grid">'
            + kpi(f'{res.get("passed",0)}/{res.get("total",0)}', "checks passed")
            + "".join(
                kpi(v, k)
                for k, v in (res.get("observed") or {}).items()
                if k in ("cells", "links", "rj_links", "bots")
            )
            + "</div>"
        )
        rows = "".join(
            f'<tr class="{"" if c.get("pass") else "bad"}"><td>{pill(c.get("pass"))}</td>'
            f'<td class="mono">{esc(c.get("check"))}</td><td>{esc(c.get("detail"))}</td></tr>'
            for c in res.get("checks", [])
        )
        out.append(
            '<div class="card scroll"><table><thead><tr><th></th><th>check</th>'
            f"<th>detail</th></tr></thead><tbody>{rows}</tbody></table></div>"
        )

    elif tier == "T1":
        el, pk = res.get("arrived_elapsed") or {}, res.get("arrived_peak_speed") or {}
        out.append(
            '<div class="grid">'
            + kpi(f'{res.get("arrived",0)}/{res.get("total",0)}', "drills arrived")
            + kpi(f'{100*res.get("arrival_rate",0):.1f}%', "arrival rate")
            + kpi(res.get("stalled", 0), "stalled")
            + kpi(res.get("errored", 0), "errored / timed out")
            + kpi(fmt(el.get("p50")) + " s", "completion p50")
            + kpi(fmt(el.get("p90")) + " s", "completion p90")
            + kpi(fmt(pk.get("p50"), 0) + " u/s", "peak speed p50")
            + kpi(fmt(pk.get("max"), 0) + " u/s", "peak speed max")
            + "</div>"
        )
        cond = env.get("conditions") or {}
        if cond:
            out.append(
                '<p class="note">Rig conditions: '
                + ", ".join(f"{esc(k)}={esc(v)}" for k, v in cond.items())
                + ". Combat is off for a puppeted bot structurally — a puppet order returns with "
                "<code>enemy: None</code> and no item chase before the pacifist branch is reached — "
                "so these drills measure movement in isolation and say nothing about movement "
                "under fire.</p>"
            )
        out.append(
            f'<p class="note">Human DM3 calibration from the step 1 corpus: ground-trim median '
            f"{HUMAN_GROUND_MEDIAN:.0f} u/s, fastest air-trim exit {HUMAN_AIR_PEAK:.0f} u/s. "
            "Cross-track drift and reverse frames are reported but <em>not</em> gated: these are "
            "full map routes, not straight corridors, so deviation from the chord is expected.</p>"
        )
        drills = res.get("drills", [])
        worst = max((d.get("metrics", {}).get("peak_speed", 0) or 0) for d in drills) if drills else 1
        rows = []
        for d in drills:
            m = d.get("metrics") or {}
            passed = bool(d.get("pass"))
            peak = m.get("peak_speed") or 0
            frac = min(1.0, peak / max(worst, 1))
            stalls = len(d.get("bot_stalls") or [])
            rows.append(
                f'<tr class="{"" if passed else "bad"}">'
                f"<td>{pill(passed, d.get('outcome'))}</td>"
                f'<td class="mono">{esc(d.get("id"))}</td>'
                f'<td>{esc(d.get("kind",""))}</td>'
                f'<td class="num">{fmt(d.get("straight_dist"),0)}</td>'
                f'<td class="num">{fmt(d.get("planned_path_len"),0)}</td>'
                f'<td class="num">{esc(d.get("planned_legs","—"))}</td>'
                f'<td class="num">{fmt(m.get("elapsed"))}</td>'
                f'<td class="num">{fmt(d.get("budget_secs"),0)}</td>'
                f'<td class="num">{fmt(peak,0)}</td>'
                f'<td><div class="bar"><i style="width:{frac*100:.0f}%"></i></div></td>'
                f'<td class="num">{fmt(m.get("max_cross_track"),0)}</td>'
                f'<td class="num">{esc(m.get("reverse_frames","—"))}</td>'
                f'<td class="num">{stalls or ""}</td>'
                "</tr>"
            )
        out.append(
            '<div class="card scroll"><table><thead><tr><th>outcome</th><th>drill</th><th>kind</th>'
            '<th class="num">chord</th><th class="num">path</th><th class="num">legs</th>'
            '<th class="num">secs</th><th class="num">budget</th><th class="num">peak u/s</th>'
            '<th></th><th class="num">drift</th><th class="num">rev</th>'
            f'<th class="num">watchdog</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        )

    b = env.get("build") or {}
    dl = []
    for key in ("engine_binary", "game_module", "build_output", "map"):
        d = b.get(key) or {}
        if d.get("md5"):
            dl.append(
                f"<dt>{esc(key)}</dt><dd class='mono'>{esc(d['md5'])} "
                f"<span style='color:var(--mut)'>{esc(os.path.basename(d.get('realpath','')))}, "
                f"{d.get('bytes',0):,} B</span></dd>"
            )
    repo = b.get("repo") or {}
    dl.append(
        f"<dt>repo</dt><dd class='mono'>{esc(repo.get('branch'))} @ "
        f"{esc((repo.get('commit') or '')[:10])}{' (dirty)' if repo.get('dirty') else ''}</dd>"
    )
    match = b.get("game_module_matches_build_output")
    dl.append(
        "<dt>module identity</dt><dd>"
        + (
            "staged qwprogs.so is byte-identical to target/release/librtx.so"
            if match
            else "<strong>MISMATCH — digests may not identify what ran</strong>"
        )
        + "</dd>"
    )
    out.append(
        f'<h3>Build under test</h3><div class="card"><div class="dl">{"".join(dl)}</div></div>'
    )
    for n in env.get("notes") or []:
        out.append(f'<p class="note">{esc(n)}</p>')
    return "\n".join(out)


def reproducibility(envs):
    """Cross-run per-drill agreement, for T1 replications sharing the same rig conditions.

    A single run's pass rate says nothing about whether an individual drill is broken or merely
    non-deterministic. Only repetition separates the two, so this panel exists to stop a one-off
    table being read as a verdict on specific drills.
    """
    # Group by the conditions that change what a drill means. Runs under different timeout floors
    # are not replications of each other and must not be pooled.
    groups = {}
    for path, e in envs:
        if e.get("tier") != "T1":
            continue
        res = e.get("result") or {}
        drills = res.get("drills") or []
        if len(drills) < 50:
            continue  # a 6-drill smoke run is not a replication
        cond = e.get("conditions") or {}
        key = (cond.get("timeout_floor_secs"), bool(cond.get("telemetry")))
        groups.setdefault(key, []).append((os.path.basename(path).removesuffix(".json"), drills))

    out = []
    for (floor, telem), runs in sorted(groups.items(), key=lambda kv: -(len(kv[1]))):
        if len(runs) < 2:
            continue
        names = [n for n, _ in runs]
        per = [{d["id"]: d for d in ds} for _, ds in runs]
        common = set(per[0])
        for p in per[1:]:
            common &= set(p)
        always_pass, always_fail, flip = [], [], []
        for did in sorted(common):
            passes = [bool(p[did].get("pass")) for p in per]
            (always_pass if all(passes) else always_fail if not any(passes) else flip).append(did)
        n = len(common)
        out.append(
            f"<h2>Reproducibility — {len(runs)} replications at a {fmt(floor,0)} s floor, "
            f"telemetry {'on' if telem else 'off'}</h2>"
        )
        out.append(
            '<div class="grid">'
            + kpi(n, "drills compared")
            + kpi(len(always_pass), "arrived every run")
            + kpi(len(always_fail), "failed every run")
            + kpi(len(flip), "flipped between runs")
            + kpi(f"{100*len(flip)/max(n,1):.0f}%", "non-deterministic")
            + "</div>"
        )
        out.append(
            f'<p class="note">Runs compared: {", ".join("<code>"+esc(x)+"</code>" for x in names)}. '
            "A drill that flips is not evidence about the map or the route — it is evidence that a "
            "single pass/fail run cannot grade it. Grading these needs repetitions per drill and a "
            "rate with a confidence interval, which is exactly what the brief already requires of "
            "route times (median over &ge;30 runs, 95% CI excluding zero).</p>"
        )
        rows = []
        for did in sorted(common, key=lambda d: (not any(bool(p[d].get("pass")) for p in per), d)):
            cells = "".join(
                f'<td>{pill(bool(p[did].get("pass")), p[did].get("outcome"))}</td>' for p in per
            )
            klass = (
                "" if all(bool(p[did].get("pass")) for p in per)
                else "bad" if not any(bool(p[did].get("pass")) for p in per)
                else ""
            )
            verdict = (
                "always arrived" if all(bool(p[did].get("pass")) for p in per)
                else "always failed" if not any(bool(p[did].get("pass")) for p in per)
                else "flaky"
            )
            rows.append(
                f'<tr class="{klass}"><td class="mono">{esc(did)}</td>{cells}'
                f"<td>{esc(verdict)}</td></tr>"
            )
        hdr = "".join(f"<th>{esc(n)}</th>" for n in names)
        out.append(
            f'<div class="card scroll"><table><thead><tr><th>drill</th>{hdr}<th>verdict</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence-dir", default="evidence")
    ap.add_argument("--output", default="dashboard.html")
    a = ap.parse_args()

    envs = []
    for p in sorted(glob.glob(os.path.join(a.evidence_dir, "*.json"))):
        if p.endswith(".raw.json"):
            continue  # raw runner output; the envelope beside it is the evidence
        try:
            with open(p) as f:
                e = json.load(f)
            if e.get("schema") == "rex-drills/1":
                envs.append((p, e))
        except (OSError, json.JSONDecodeError) as err:
            print(f"  skipping {p}: {err}")

    envs.sort(key=lambda pe: str(pe[1].get("tier")))
    tiers = ", ".join(str(e.get("tier")) for _, e in envs) or "none"
    allok = envs and all(e.get("status") == "passed" for _, e in envs)
    m = (envs[0][1].get("machine") if envs else {}) or {}

    body = [
        '<div class="wrap">',
        "<h1>rtx live test — local rig</h1>",
        f'<p class="sub">Tiers present: {esc(tiers)} · '
        f'{esc(m.get("host",""))} · {esc(m.get("kernel",""))} · '
        f'{esc(m.get("cpus","?"))} cpus · overall {pill(bool(allok))}</p>',
        '<div class="card banner"><strong>This is not <code>rtx-testflow/1</code> evidence.</strong> '
        "The lab suite on <code>lanister:projects/quakeworld/rtx@testsuite</code> could not be "
        "reached from this machine (hostname does not resolve; the public remote has no "
        "<code>testsuite</code> branch), so these envelopes use the schema id "
        "<code>rex-drills/1</code> and must not be compared with suite results. T2–T4 were not "
        "run — see <code>livetest/README.md</code>.</div>",
    ]
    if not envs:
        body.append('<div class="card">No evidence envelopes found.</div>')
    for p, e in envs:
        body.append(build_section(e, p))
        body.append(f'<p class="note">Source: <code>{esc(p)}</code></p>')
    body.extend(reproducibility(envs))
    body.append("</div>")

    doc = (
        "<!doctype html><html><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        "<title>rtx live test — local rig</title>"
        f"<style>{CSS}</style></head><body>{''.join(body)}</body></html>"
    )
    with open(a.output, "w") as f:
        f.write(doc)
    print(f"{a.output}: {len(envs)} envelope(s), tiers {tiers}")


if __name__ == "__main__":
    main()
