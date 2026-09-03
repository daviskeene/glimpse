import { Check, Copy } from "lucide-react";
import { useCopy } from "@/lib/useCopy";
import { cn } from "@/lib/utils";

export function CopyButton({ text, className, label = "Copy" }: { text: string; className?: string; label?: string }) {
  const { copied, copy } = useCopy(text);
  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? "Copied" : label}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-petrol-line px-2 py-1 font-mono text-[11px] text-mist transition-colors hover:border-mist hover:text-white",
        className,
      )}
    >
      {copied ? <Check className="h-3 w-3 text-mint" /> : <Copy className="h-3 w-3" />}
      {copied ? "copied" : label}
    </button>
  );
}

export default function CodeBlock({
  code,
  title,
  className,
}: {
  code: string;
  title?: string;
  className?: string;
}) {
  return (
    <div className={cn("overflow-hidden rounded-lg border border-petrol-line bg-petrol text-[13px]", className)}>
      <div className="flex items-center justify-between border-b border-petrol-line/70 px-3 py-1.5">
        <span className="font-mono text-[11px] text-mist">{title ?? ""}</span>
        <CopyButton text={code} />
      </div>
      <pre className="scrollbar-thin overflow-x-auto px-4 py-3 font-mono leading-relaxed text-[#E6EEEC]">
        <code>{code}</code>
      </pre>
    </div>
  );
}
