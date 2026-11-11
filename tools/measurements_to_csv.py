#!/usr/bin/env python3
"""Turn nornCore's measurement summaries (doc/measurements/*.md, written by
tools/measure.sh) into the CSV files the user guide's pgfplots graphs read.

    tools/measurements_to_csv.py [NORNRTOS] [OUTDIR]

NORNRTOS defaults to ../nornRTOS, OUTDIR to guide/data. The latest summary (by its
"Taken" date, else file time) feeds the per-primitive graphs; the history graphs take
every label in HISTORY that exists.
"""
import os, re, sys, glob, datetime

HISTORY = [  # label, short caption; the "before" copies are left out (identical kernels)
    ("baseline",              "baseline"),
    ("step2-f1",              "F1"),
    ("step3-f2",              "F2"),
    ("step3b-sched",          "sched"),
    ("step4-small",           "F3/F7"),
    ("step5-timeout",         "F6"),
    ("step6-after",           "F9-F11"),
    ("step7-amp",             "F4"),
    ("step8-tie-after",       "tie"),
    ("step9-curboost-after",  "boost"),
    ("step10-lifecycle-after","lifecycle"),
]
API_ROWS = ["critical section", "getTick", "sem give+take", "notify set+wait",
            "mutex lock+unlock", "queue send+recv", "mbox post+fetch", "pool alloc+free",
            "evgroup set+wait", "timer start+stop", "events post+wait", "getTimeUs",
            "getCpuLoad", "sem give+take, ceiling held"]
BOARDS = ["mega2560", "esp32"]

def sections(text):
    """{heading: body} for the '## ' headings of a summary."""
    out, cur, buf = {}, None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if cur: out[cur] = "\n".join(buf)
            cur, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if cur: out[cur] = "\n".join(buf)
    return out

def taken(text, path):
    m = re.search(r"Taken (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", text)
    if m: return datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
    return datetime.datetime.fromtimestamp(os.path.getmtime(path))

def sizes(sec):
    out = {}
    for m in re.finditer(r"^\| (uno|mega2560|esp32) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|",
                         sec, re.M):
        out[m.group(1)] = dict(text=int(m.group(2)), data=int(m.group(3)), bss=int(m.group(4)),
                               ktext=int(m.group(5)))
    return out

def tc10(sec):
    """api {name: cycles}, switch {name: (min, avg)}, isr {name: (min, avg, max)}, ram {...}."""
    api, sw, isr, ram = {}, {}, {}, {}
    for m in re.finditer(r"^    ([a-zA-Z ,+>-]+): (\d+)$", sec, re.M):
        api[m.group(1).strip()] = int(m.group(2))
    for m in re.finditer(r"^    (sem|notify|queue|events): (\d+)/(\d+) cycles", sec, re.M):
        sw[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    for m in re.finditer(r"^    (isr->task [a-z ,]+?):\s+(\d+)/(\d+)/(\d+) cycles", sec, re.M):
        isr[m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    m = re.search(r"entry:\s+(\d+)/(\d+)/(\d+) counts = (\d+)/(\d+)/(\d+) ns", sec)
    if m: isr["entry ns"] = (int(m.group(4)), int(m.group(5)), int(m.group(6)))
    m = re.search(r"tcb (\d+) x \d+, sem (\d+), mutex (\d+), queue (\d+), mbox (\d+), pool (\d+), timer (\d+), evgroup (\d+)", sec)
    if m:
        for k, v in zip(["tcb", "sem", "mutex", "queue", "mbox", "pool", "timer", "evgroup"], m.groups()):
            ram[k] = int(v)
    m = re.search(r"min stack (\d+), stack used of (\d+): wake (\d+), high (\d+), low (\d+)", sec)
    if m: ram["minstack"], ram["stacksize"], ram["wake"], ram["high"], ram["low"] = map(int, m.groups())
    return api, sw, isr, ram

def tc11(sec):
    out = {}
    for m in re.finditer(r"^  (block|wake|busy|script)\s+(\d+)$", sec, re.M):
        out[m.group(1)] = int(m.group(2))
    return out

def tc12(sec):
    """phase letter -> [used at depth 0,4,8,16,32], plus kernel share per phase."""
    out = {}
    for m in re.finditer(r"^  ([A-D]) ([^\n]*?)\s+used ((?:\d+[ \t]*){5})(?:kernel\+port ((?:\d+[ \t]*){5}))?", sec, re.M):
        out[m.group(1)] = dict(name=m.group(2).strip(), used=[int(x) for x in m.group(3).split()],
                               kernel=[int(x) for x in m.group(4).split()] if m.group(4) else None)
    return out

def write(path, header, rows):
    with open(path, "w") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")

def main():
    nornrtos = sys.argv[1] if len(sys.argv) > 1 else "../nornRTOS"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "guide/data"
    mdir = os.path.join(nornrtos, "modules/nornCore/doc/measurements")
    files = {}
    for p in glob.glob(os.path.join(mdir, "*.md")):
        text = open(p).read()
        files[os.path.basename(p)[:-3]] = dict(path=p, text=text, taken=taken(text, p),
                                               sec=sections(text))
    if not files:
        sys.exit("no measurement summaries in " + mdir)
    os.makedirs(outdir, exist_ok=True)
    latest = max(files.values(), key=lambda f: f["taken"])
    label = os.path.basename(latest["path"])[:-3]
    print("latest:", label, latest["taken"].strftime("%Y-%m-%d"))
    with open(os.path.join(outdir, "latest.tex"), "w") as f:
        f.write("\\newcommand{\\measLabel}{%s}\n\\newcommand{\\measDate}{%s}\n"
                % (label.replace("_", "\\_"), latest["taken"].strftime("%Y-%m-%d")))

    # per board latest tc10
    per = {b: tc10(latest["sec"].get("tc10 " + b, "")) for b in BOARDS}
    write(os.path.join(outdir, "api.csv"), ["call", "mega2560", "esp32"],
          [[name.replace(",", ";"), per["mega2560"][0].get(name, ""), per["esp32"][0].get(name, "")]
           for name in API_ROWS if name in per["mega2560"][0] or name in per["esp32"][0]])
    write(os.path.join(outdir, "switch.csv"), ["mechanism", "megamin", "megaavg", "espmin", "espavg"],
          [[k, *per["mega2560"][1].get(k, ("", "")), *per["esp32"][1].get(k, ("", ""))]
           for k in ["sem", "notify", "queue", "events"]])
    isrrows = []
    for k in ["isr->task sem", "isr->task notify", "isr->task notify, ceiling held"]:
        a, b = per["mega2560"][2].get(k, ("", "", "")), per["esp32"][2].get(k, ("", "", ""))
        isrrows.append([k.replace("isr->task ", "").replace(",", ";"), *a, *b])
    write(os.path.join(outdir, "isr.csv"), ["path", "megamin", "megaavg", "megamax", "espmin", "espavg", "espmax"], isrrows)
    write(os.path.join(outdir, "ram.csv"), ["object", "mega2560", "esp32"],
          [[k, per["mega2560"][3].get(k, ""), per["esp32"][3].get(k, "")]
           for k in ["tcb", "sem", "mutex", "queue", "mbox", "pool", "timer", "evgroup"]])
    write(os.path.join(outdir, "stack11.csv"), ["task", "mega2560", "esp32"],
          [[k, tc11(latest["sec"].get("tc11 mega2560", "")).get(k, ""),
            tc11(latest["sec"].get("tc11 esp32", "")).get(k, "")] for k in ["block", "wake", "busy", "script"]])
    for b in BOARDS:
        t = tc12(latest["sec"].get("tc12 " + b, ""))
        rows = []
        for i, d in enumerate([0, 4, 8, 16, 32]):
            rows.append([d] + [t[p]["used"][i] if p in t else "" for p in "ABCD"])
        write(os.path.join(outdir, "stack12-%s.csv" % b), ["depth", "A", "B", "C", "D"], rows)

    # history
    rows = []
    for lab, short in HISTORY:
        if lab not in files: continue
        f = files[lab]
        sz = sizes(f["sec"].get("Size (bytes), tc01", ""))
        m, e = tc10(f["sec"].get("tc10 mega2560", "")), tc10(f["sec"].get("tc10 esp32", ""))
        rows.append([len(rows), short, lab,
                     sz.get("uno", {}).get("text", ""), sz.get("mega2560", {}).get("text", ""),
                     sz.get("esp32", {}).get("text", ""),
                     m[1].get("sem", ("", ""))[0], e[1].get("sem", ("", ""))[0],
                     m[2].get("isr->task sem", ("", "", ""))[0], e[2].get("isr->task sem", ("", "", ""))[0],
                     m[0].get("sem give+take", ""), e[0].get("sem give+take", "")])
    write(os.path.join(outdir, "history.csv"),
          ["n", "step", "label", "unotext", "megatext", "esptext", "megaswitch", "espswitch",
           "megaisr", "espisr", "megasem", "espsem"], rows)
    # the example listed in the guide, copied so that the guide builds on its own
    src = os.path.join(nornrtos, "examples/hello/hello.c")
    if os.path.exists(src):
        with open(src) as f, open(os.path.join(outdir, "hello.c"), "w") as g:
            g.write(f.read())
    print("wrote", outdir, "(%d history points)" % len(rows))

if __name__ == "__main__":
    main()
