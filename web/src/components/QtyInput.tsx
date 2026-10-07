"use client";

export default function QtyInput({ value, onChange, onCommit, pink = false, className = "", placeholder = "-" }: {
  value: number; onChange: (n: number) => void; onCommit?: () => void; pink?: boolean; className?: string; placeholder?: string;
}) {
  return (
    <input
      type="text" inputMode="numeric" pattern="[0-9]*"
      className={`qty ${pink ? "qty-pink" : ""} ${className}`}
      value={value > 0 ? String(value) : ""}
      placeholder={placeholder}
      onFocus={(e) => e.currentTarget.select()}
      onBlur={onCommit}
      onKeyDown={(e) => { if (e.key === "Enter" && onCommit) { e.preventDefault(); onCommit(); } }}
      onChange={(e) => {
        const n = parseInt(e.target.value.replace(/\D/g, ""), 10);
        onChange(Number.isFinite(n) ? Math.min(n, 99999) : 0);
      }}
    />
  );
}
