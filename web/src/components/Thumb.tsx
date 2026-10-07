export default function Thumb({ src, alt = "", className = "" }: { src: string | null | undefined; alt?: string; className?: string }) {
  if (!src) return <div className={`bg-[#f1f1f1] ${className}`} aria-hidden />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} loading="lazy" className={className} />;
}
