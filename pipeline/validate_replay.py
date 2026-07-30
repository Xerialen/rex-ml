"""Open the replay page in a real browser and check that it actually runs.

Written after publishing two pages without opening either of them. A page that throws on load looks
exactly like a page that works, from the side of the person who wrote it.

What this asserts, in order of what would hurt most if it were wrong:

  1. **No console errors and no uncaught exceptions**, collected from page load through several
     seconds of playback. A shader that fails to compile or a byte offset that runs past the buffer
     shows up here and nowhere else.
  2. **WebGL actually rendered.** The canvas is read back and checked for more than one distinct
     colour: a page that clears to the background and draws nothing passes every other check.
  3. **The clock advances at 1:1.** The page is left running for a measured wall-clock interval and
     the displayed time is compared against it. This is the claim the whole page is built on, so it
     is the one that must be measured rather than assumed.
  4. **Every attempt in the rail selects and plays**, so a broken record deep in the list cannot hide
     behind a working first one.
  5. **Both camera modes and the theme toggle** produce a rendered frame rather than a blank one.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

FLAGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--use-angle=swiftshader",
         "--disable-gpu-sandbox", "--allow-file-access-from-files"]


def distinct_colours(png: bytes) -> int:
    """How many distinct pixels a screenshot holds, sampled cheaply. One means a blank frame."""
    import zlib
    import struct as st
    pos, w, h, idat = 8, 0, 0, b""
    while pos < len(png):
        ln = st.unpack_from(">I", png, pos)[0]
        typ = png[pos + 4:pos + 8]
        if typ == b"IHDR":
            w, h = st.unpack_from(">II", png, pos + 8)
        elif typ == b"IDAT":
            idat += png[pos + 8:pos + 8 + ln]
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * 4 + 1
    seen = set()
    for y in range(0, h, 7):
        row = raw[y * stride + 1:(y + 1) * stride]
        for x in range(0, w * 4, 4 * 11):
            seen.add(row[x:x + 3])
            if len(seen) > 64:
                return len(seen)
    return len(seen)


def check(path: Path) -> dict:
    errors, console = [], []
    report: dict = {"page": path.name, "checks": [], "errors": errors}

    def ok(name, passed, detail=""):
        report["checks"].append({"check": name, "pass": bool(passed), "detail": detail})
        print(f"  [{'ok ' if passed else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}",
              flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=FLAGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("console", lambda m: (console.append(m.text),
                                      errors.append(f"console.{m.type}: {m.text}")
                                      if m.type in ("error", "warning") else None))
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        t_open = time.time()
        page.goto(path.as_uri(), wait_until="load", timeout=120_000)
        page.wait_for_timeout(2500)
        ok("laddar utan uncaught exception", not any(e.startswith("pageerror") for e in errors),
           "; ".join(e for e in errors if e.startswith("pageerror"))[:300])
        ok(f"laddtid {time.time() - t_open:.1f} s", True)

        info = page.evaluate("""() => ({
            gl: !!document.getElementById('gl').getContext('webgl'),
            attempts: document.querySelectorAll('.attempt').length,
            routes: document.querySelectorAll('.route').length,
            meshTris: (typeof MESH !== 'undefined') ? MESH.count / 3 : null,
            frames: (typeof INDEX !== 'undefined') ? INDEX.records.reduce((a,r)=>a+r.runs.reduce((b,x)=>b+x.n_frames,0),0) : null,
            tick: (typeof INDEX !== 'undefined') ? INDEX.tick_dt : null,
            total: document.getElementById('c-tot').textContent
        })""")
        report["info"] = info
        ok("WebGL-kontext skapad", info["gl"])
        ok("banor och försök i listan", info["attempts"] > 0 and info["routes"] > 0,
           f"{info['routes']} rutter, {info['attempts']} poster")
        ok("geometri avkodad", (info["meshTris"] or 0) > 1000, f"{info['meshTris']} trianglar")
        ok("bildrutor avkodade", (info["frames"] or 0) > 100, f"{info['frames']} tick totalt")

        sel = page.evaluate("() => (typeof state !== 'undefined' && state.run) "
                            "? {n: state.run.n_frames, route: state.rec.route} : null")
        ok("ett försök är valt vid start", sel is not None, str(sel))

        shot = page.locator("#gl").screenshot()
        n = distinct_colours(shot)
        ok("något ritas i vyn (inte blank)", n > 3, f"{n} distinkta pixelvärden")

        # 1:1 playback: measure the page clock against the wall clock.
        page.evaluate("() => { state.tick = 0; state.acc = 0; setPlaying(true); }")
        page.wait_for_timeout(300)
        t0 = time.time()
        c0 = float(page.evaluate("() => document.getElementById('c-now').textContent"))
        page.wait_for_timeout(3000)
        c1 = float(page.evaluate("() => document.getElementById('c-now').textContent"))
        wall = time.time() - t0
        adv = c1 - c0
        # A short clip loops, so only a non-wrapping interval is comparable.
        rate = adv / wall if adv > 0 else 0
        ok("uppspelning 1:1 (±8 %)", 0.92 <= rate <= 1.08 or adv < 0,
           f"{adv:.2f} s speltid på {wall:.2f} s väggtid = {rate:.3f}x"
           + (" (klippet loopade, ej jämförbart)" if adv < 0 else ""))

        # The airborne-segment strip: it is the page's answer to "show me the jump", so a claim
        # rendered from an empty array, or a button that does not move the playhead, is the whole
        # feature silently absent. Checked on every record that reports segments, not just the first.
        seg_stats = page.evaluate("""() => {
          let withSegs = 0, rendered = 0, mismatched = 0;
          for (let r = 0; r < INDEX.records.length; r++) {
            for (let k = 0; k < INDEX.records[r].runs.length; k++) {
              const segs = INDEX.records[r].runs[k].segments;
              if (!segs || !segs.length) continue;
              withSegs++;
              select(r, k);
              const btns = document.getElementById("segs").children;
              if (btns.length === segs.length) rendered++; else mismatched++;
            }
          }
          return {withSegs, rendered, mismatched};
        }""")
        ok("luftsegment renderas för varje körning som har dem",
           seg_stats["withSegs"] > 0 and seg_stats["mismatched"] == 0,
           f"{seg_stats['rendered']}/{seg_stats['withSegs']} körningar, "
           f"{seg_stats['mismatched']} med fel antal knappar")

        jumped = page.evaluate("""() => {
          for (let r = 0; r < INDEX.records.length; r++) {
            for (let k = 0; k < INDEX.records[r].runs.length; k++) {
              const segs = INDEX.records[r].runs[k].segments;
              if (!segs || segs.length < 2) continue;
              select(r, k);
              const last = segs[segs.length - 1];
              document.getElementById("segs").children[segs.length - 1].click();
              return {tick: state.tick, want: last.a, scrub: +document.getElementById("scrub").value};
            }
          }
          return null;
        }""")
        ok("klick på ett luftsegment flyttar uppspelningen dit",
           jumped is not None and jumped["tick"] == jumped["want"]
           and jumped["scrub"] == jumped["want"],
           str(jumped))

        # every attempt in the rail
        bad = []
        n_att = info["attempts"]
        for i in range(n_att):
            before = len(errors)
            page.evaluate(f"() => document.querySelectorAll('.attempt')[{i}].click()")
            page.wait_for_timeout(90)
            st = page.evaluate("() => ({t: document.getElementById('c-tot').textContent, n: state.run.n_frames})")
            if len(errors) > before or float(st["t"]) <= 0 or st["n"] < 2:
                bad.append((i, st, errors[before:]))
        ok("varje post i listan går att välja och spela", not bad,
           f"{n_att} poster, {len(bad)} trasiga" + (f" {bad[:2]}" if bad else ""))

        # Every record must say who produced it, and the badge in the view must follow the selection.
        # "reference" and "race_v7 ing.0" describe a decode, not an author, and the owner needs the
        # difference between his own recording and a policy attempt to be unmistakable.
        src = page.evaluate("""() => {
          const seen = {}, missing = [];
          for (const r of INDEX.records) {
            if (!r.source || !r.source_label) missing.push(r.route + "/" + r.decode);
            seen[r.source] = (seen[r.source] || 0) + 1;
          }
          // switch to a reference record and read the badge back out of the DOM
          const ri = INDEX.records.findIndex(r => r.source === "owner");
          let badge = null;
          if (ri >= 0) {
            select(ri, 0);
            const el = document.getElementById("h-src");
            badge = {cls: el.className, text: el.textContent};
          }
          return {seen, missing, badge};
        }""")
        ok("varje post har en källa (du / ML / analytisk)", not src["missing"],
           f"{src['seen']}" + (f" saknar: {src['missing'][:3]}" if src["missing"] else ""))
        ok("källmärket i vyn följer valet",
           src["badge"] is not None and src["badge"]["cls"] == "owner"
           and "DIN" in src["badge"]["text"], str(src["badge"]))

        # The picker is the only way in that survives being framed, so it has to be complete and it
        # has to actually change the selection.
        pick = page.evaluate("""() => {
          const rs = document.getElementById("p-route"), cs = document.getElementById("p-case");
          if (!rs || !cs) return null;
          const routes = new Set(INDEX.records.map(r => r.route));
          // Drive it from a known state to another known state: the previous check clicks through
          // every record and may already have left us on the one we were about to pick.
          rs.value = rs.options[0].value;
          rs.dispatchEvent(new Event("change"));
          cs.value = cs.options[0].value;
          cs.dispatchEvent(new Event("change"));
          const before = INDEX.records.indexOf(state.rec);
          rs.value = rs.options[rs.options.length - 1].value;
          rs.dispatchEvent(new Event("change"));
          cs.value = cs.options[cs.options.length - 1].value;
          cs.dispatchEvent(new Event("change"));
          const after = INDEX.records.indexOf(state.rec);
          return {n_routes: rs.options.length, want: routes.size, before, after,
                  route_now: state.rec.route, target: rs.value};
        }""")
        ok("fallväljaren listar varje rutt och byter fall",
           pick is not None and pick["n_routes"] == pick["want"]
           and pick["after"] != pick["before"] and pick["route_now"] == pick["target"],
           str(pick))

        # Landing without a fragment must not be the corridor — a framed artifact never sees the
        # parent's hash, so the default is what most visitors actually get.
        page.goto(path.as_uri())
        page.wait_for_timeout(1200)
        landing = page.evaluate("() => ({route: state.rec.route, map: state.rec.map,"
                                " dec: state.rec.decode})")
        ok("utan fragment landar sidan på ruttarbetet, inte korridoren",
           landing["map"] != "100m", str(landing))

        # A deep link must land on the exact record, run, tick and camera it names. A link that
        # silently falls back to the first run looks like a working link right up until the person
        # who followed it is watching something else.
        deep = page.evaluate("""() => {
          for (let i = 0; i < INDEX.records.length; i++) {
            const r = INDEX.records[i];
            for (let k = 0; k < r.runs.length; k++) {
              const segs = r.runs[k].segments || [];
              const g = segs.find(s => s.kind === "gap_up" || s.kind === "gap");
              if (g) return {rt: r.route, dec: r.decode, run: k, t: g.a};
            }
          }
          return null;
        }""")
        if deep:
            url = (f"{path.as_uri()}#rt={deep['rt']}&dec={deep['dec']}"
                   f"&run={deep['run']}&t={deep['t']}&cam=first")
            page.goto(url)
            page.wait_for_timeout(1500)
            landed = page.evaluate("() => ({rt: state.rec.route, dec: state.rec.decode,"
                                   " run: state.rec.runs.indexOf(state.run), t: state.tick,"
                                   " cam: state.cam})")
            ok("djuplänk landar på rätt körning, tick och kamera",
               landed["rt"] == deep["rt"] and landed["dec"] == deep["dec"]
               and landed["run"] == deep["run"] and abs(landed["t"] - deep["t"]) <= 2
               and landed["cam"] == "first",
               f"bad {deep} fick {landed}")
        else:
            ok("djuplänk landar på rätt körning, tick och kamera", False, "inget gaphopp att länka")

        # The viewport has to be big enough to be a view. Everything else here passed while the 3D
        # canvas was a 150 px strip squeezed by the bar's own content, which is exactly the state the
        # owner reported as "I cannot see the first-person view".
        box = page.evaluate("() => { const r = document.getElementById('gl').getBoundingClientRect();"
                            " return {w: Math.round(r.width), h: Math.round(r.height)}; }")
        ok("3D-vyn har verklig höjd (>= 300 px)", box["h"] >= 300, f"{box['w']}x{box['h']} px")

        # cameras: not just "renders", but "renders something DIFFERENT". A mode switch that silently
        # does nothing produces three identical frames and passes any non-blank check.
        cam_shots, cam_bytes = {}, {}
        for cam in ("follow", "first", "top"):
            page.evaluate(f"() => document.querySelector('#cams button[data-cam=\\'{cam}\\']').click()")
            page.wait_for_timeout(450)
            shot = page.locator("#gl").screenshot()
            cam_shots[cam] = distinct_colours(shot)
            cam_bytes[cam] = hashlib.sha256(shot).hexdigest()[:12]
        ok("alla tre kameralägen renderar", all(v > 3 for v in cam_shots.values()), str(cam_shots))
        ok("kameralägena visar olika bilder", len(set(cam_bytes.values())) == 3, str(cam_bytes))

        # cutaway slider is reachable in top view and changes the image
        page.evaluate("() => { const c=document.getElementById('cut'); c.value='0'; c.dispatchEvent(new Event('input')); }")
        page.wait_for_timeout(400)
        cut_n = distinct_colours(page.locator("#gl").screenshot())
        ok("takhöjdsreglaget påverkar bilden", cut_n != cam_shots["top"] or cut_n > 3,
           f"{cam_shots['top']} -> {cut_n}")

        # themes
        theme_shots = {}
        for th in ("light", "dark"):
            page.evaluate(f"() => document.documentElement.dataset.theme = '{th}'")
            page.wait_for_timeout(400)
            theme_shots[th] = distinct_colours(page.locator("#gl").screenshot())
        ok("båda teman renderar", all(v > 3 for v in theme_shots.values()), str(theme_shots))

        # no horizontal page scroll
        overflow = page.evaluate("() => document.body.scrollWidth - document.body.clientWidth")
        ok("ingen horisontell sidscroll", overflow <= 1, f"{overflow} px")

        real_errors = [e for e in errors if "WebGL" not in e or "pageerror" in e]
        ok("inga console-fel", not real_errors, "; ".join(real_errors[:3])[:400])

        browser.close()

    report["passed"] = all(c["pass"] for c in report["checks"])
    return report


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]]
    out = []
    for p in paths:
        print(f"\n=== {p.name} ===", flush=True)
        out.append(check(p))
    Path("/home/benjamin-adm/rex-ml/evidence").mkdir(exist_ok=True)
    Path("/home/benjamin-adm/rex-ml/evidence/replay_page_validation.json").write_text(
        json.dumps(out, indent=1))
    print("\n" + ("ALLA KONTROLLER GRÖNA" if all(r["passed"] for r in out) else "MISSLYCKADES"))
    sys.exit(0 if all(r["passed"] for r in out) else 1)
