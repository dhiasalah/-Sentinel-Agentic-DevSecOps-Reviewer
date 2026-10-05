import { Fragment } from "react";

// Models answer in Markdown. This renders the two parts that matter here, fenced code and `inline code`, and keeps
// line breaks. Everything stays a React text node (escaped): the text was written by a model that read a pull request.
export function AiText({ text, className = "" }: { text: string; className?: string }) {
  const parts = text.split(/```[^\n`]*\n?([\s\S]*?)```/g);
  return (
    <div className={`space-y-3 ${className}`}>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <pre
            key={i}
            className="overflow-x-auto rounded-[4px] border border-rule bg-surface px-3 py-2.5 font-mono text-[12.5px] leading-[1.7] whitespace-pre"
          >
            <code>{part.replace(/\n$/, "")}</code>
          </pre>
        ) : (
          part.trim() && (
            <p key={i} className="whitespace-pre-line [overflow-wrap:anywhere]">
              <Inline text={part.trim()} />
            </p>
          )
        ),
      )}
    </div>
  );
}

function Inline({ text }: { text: string }) {
  return text.split(/`([^`\n]+)`/g).map((piece, i) =>
    i % 2 === 1 ? (
      <code key={i} className="rounded-[3px] bg-surface px-1 py-px font-mono text-[0.9em] ring-1 ring-rule">
        {piece}
      </code>
    ) : (
      <Fragment key={i}>{piece}</Fragment>
    ),
  );
}
