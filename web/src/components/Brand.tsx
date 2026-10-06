import Link from "next/link";

export function Wordmark({ href = "/h/marro" }: { href?: string }) {
  return (
    <Link href={href} className="font-brand text-[24px] font-extrabold tracking-[0.02em] leading-none text-ink">LAUTIN</Link>
  );
}

export function Chimola({ className = "" }: { className?: string }) {
  return (
    <span className={`font-brand font-bold lowercase leading-none ${className}`}>chimola<span className="align-top text-[0.55em]">®</span></span>
  );
}

export function Lima({ className = "" }: { className?: string }) {
  return <span className={`font-serif leading-none tracking-[0.06em] ${className}`}>LIMA</span>;
}

export function CameraIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" className={className} aria-hidden>
      <path d="M4 8h3l1.5-2h7L17 8h3v11H4z" /><circle cx="12" cy="13" r="3.2" /><path d="M19 4v3M17.5 5.5h3" />
    </svg>
  );
}

export function UserIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" />
    </svg>
  );
}

export function CartIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden>
      <path d="M7 18a2 2 0 1 0 0 4 2 2 0 0 0 0-4Zm10 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM3 3h2.4l2.6 10.2A2 2 0 0 0 10 15h8.3a2 2 0 0 0 1.9-1.4L22 6H6.3L5.6 3.6A1 1 0 0 0 4.6 3H3Z" />
    </svg>
  );
}

export function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" />
    </svg>
  );
}

export function Chevron({ dir = "right", size = 22 }: { dir?: "left" | "right" | "down" | "up"; size?: number }) {
  const rot = { right: 0, down: 90, left: 180, up: 270 }[dir];
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.4" style={{ transform: `rotate(${rot}deg)` }} aria-hidden>
      <path d="m9 5 7 7-7 7" />
    </svg>
  );
}

export function XIcon({ size = 18 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}
