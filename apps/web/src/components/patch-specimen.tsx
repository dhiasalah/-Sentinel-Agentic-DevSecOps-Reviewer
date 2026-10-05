// A real fix from Sentinel's benchmark run (step 6.3), shown as it reached the reviewer.
const lines: { kind: "ctx" | "del" | "add"; n: [number | null, number | null]; text: string }[] = [
  { kind: "ctx", n: [9, 9], text: "" },
  { kind: "ctx", n: [10, 10], text: "def load_config(text: str):" },
  { kind: "del", n: [11, null], text: "    return yaml.load(text, Loader=yaml.Loader)" },
  { kind: "add", n: [null, 11], text: "    return yaml.safe_load(text)" },
  { kind: "ctx", n: [12, 12], text: "" },
  { kind: "ctx", n: [13, 13], text: "" },
  { kind: "ctx", n: [14, 14], text: "def load_defaults(text: str):" },
];

const rowStyle = {
  ctx: "",
  del: "bg-del-bg text-del-ink",
  add: "bg-add-bg text-add-ink",
};

const sign = { ctx: " ", del: "−", add: "+" };

export function PatchSpecimen() {
  return (
    <figure className="overflow-hidden rounded-[6px] border border-rule bg-surface shadow-[0_1px_0_rgba(23,25,30,0.04),0_24px_48px_-24px_rgba(23,25,30,0.18)]">
      <figcaption className="flex items-center justify-between border-b border-rule px-4 py-3">
        <span className="font-mono text-[12px]">app/serialize.py</span>
        <span className="font-mono text-[11px] tracking-[0.06em] text-muted uppercase">Proposed fix</span>
      </figcaption>

      <div className="overflow-x-auto py-2 font-mono text-[12.5px] leading-[1.75]">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, i) => (
              <tr key={i} className={rowStyle[line.kind]}>
                <td className="w-9 pr-2 text-right text-[11px] text-muted/70 tabular-nums select-none">{line.n[0] ?? ""}</td>
                <td className="w-9 pr-2 text-right text-[11px] text-muted/70 tabular-nums select-none">{line.n[1] ?? ""}</td>
                <td className="w-5 text-center select-none">{sign[line.kind]}</td>
                <td className="pr-4 whitespace-pre">{line.text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <dl className="grid grid-cols-3 border-t border-rule text-[12px]">
        <div className="border-r border-rule px-4 py-3">
          <dt className="font-mono text-[10.5px] tracking-[0.06em] text-muted uppercase">Sandbox</dt>
          <dd className="mt-1 flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-signal" aria-hidden="true" />
            Verified
          </dd>
        </div>
        <div className="border-r border-rule px-4 py-3">
          <dt className="font-mono text-[10.5px] tracking-[0.06em] text-muted uppercase">Re-scanned</dt>
          <dd className="mt-1">gitleaks, semgrep</dd>
        </div>
        <div className="px-4 py-3">
          <dt className="font-mono text-[10.5px] tracking-[0.06em] text-muted uppercase">Patch</dt>
          <dd className="mt-1 font-mono">03cf51fe1631</dd>
        </div>
      </dl>
    </figure>
  );
}
