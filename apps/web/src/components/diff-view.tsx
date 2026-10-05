type Row = { kind: "ctx" | "del" | "add" | "hunk"; old: number | null; new: number | null; text: string };
type FileDiff = { name: string; rows: Row[] };

// Parses the unified diffs Sentinel produces (difflib / git format). Anything unexpected is shown as context.
export function parseDiff(diff: string): FileDiff[] {
  const files: FileDiff[] = [];
  let file: FileDiff | null = null;
  let oldLine = 0;
  let newLine = 0;
  for (const line of diff.replace(/\r\n/g, "\n").split("\n")) {
    if (line.startsWith("--- ")) continue;
    if (line.startsWith("+++ ")) {
      file = { name: line.slice(4).replace(/^b\//, ""), rows: [] };
      files.push(file);
      continue;
    }
    if (!file) continue;
    const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);
    if (hunk) {
      oldLine = Number(hunk[1]);
      newLine = Number(hunk[2]);
      file.rows.push({ kind: "hunk", old: null, new: null, text: line });
    } else if (line.startsWith("-")) {
      file.rows.push({ kind: "del", old: oldLine++, new: null, text: line.slice(1) });
    } else if (line.startsWith("+")) {
      file.rows.push({ kind: "add", old: null, new: newLine++, text: line.slice(1) });
    } else if (line.startsWith(" ")) {
      file.rows.push({ kind: "ctx", old: oldLine++, new: newLine++, text: line.slice(1) });
    }
  }
  return files;
}

const ROW = { ctx: "", del: "bg-del-bg text-del-ink", add: "bg-add-bg text-add-ink", hunk: "bg-paper text-muted" };
const SIGN = { ctx: " ", del: "−", add: "+", hunk: "" };

export function DiffView({ diff }: { diff: string }) {
  return (
    <div className="space-y-6">
      {parseDiff(diff).map((file) => (
        <figure key={file.name} className="overflow-hidden rounded-[6px] border border-rule bg-surface">
          <figcaption className="border-b border-rule px-4 py-3 font-mono text-[12px]">{file.name}</figcaption>
          <div className="overflow-x-auto py-1 font-mono text-[12.5px] leading-[1.75]">
            <table className="w-full border-collapse">
              <tbody>
                {file.rows.map((row, i) => (
                  <tr key={i} className={ROW[row.kind]}>
                    <td className="w-10 pr-2 text-right text-[11px] text-muted/70 tabular-nums select-none">{row.old ?? ""}</td>
                    <td className="w-10 pr-2 text-right text-[11px] text-muted/70 tabular-nums select-none">{row.new ?? ""}</td>
                    <td className="w-5 text-center select-none">{SIGN[row.kind]}</td>
                    <td className="pr-4 whitespace-pre">{row.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </figure>
      ))}
    </div>
  );
}
