/**
 * Aurum's mark: a coin with an "A" monogram. Rendered as inline SVG (not the
 * 🜚 alchemical-gold emoji this replaced) because emoji glyph coverage for
 * that character is inconsistent across platforms/fonts and rendered
 * mangled for the user — an SVG always looks the same everywhere. Kept in
 * sync with public/favicon.svg.
 */
interface LogoProps {
  size?: number;
  className?: string;
}

export function Logo({ size = 24, className }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="aurumCoin" x1="5" y1="4" x2="27" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#f7d488" />
          <stop offset="0.55" stopColor="#eda100" />
          <stop offset="1" stopColor="#a8690a" />
        </linearGradient>
      </defs>
      <circle cx="16" cy="16" r="14.5" fill="url(#aurumCoin)" stroke="#7a4e08" strokeWidth="1.2" />
      <circle cx="16" cy="16" r="11.5" fill="none" stroke="#7a4e08" strokeWidth="0.6" opacity="0.45" />
      <text
        x="16"
        y="21.5"
        fontFamily="Georgia, 'Times New Roman', serif"
        fontSize="15"
        fontWeight="700"
        textAnchor="middle"
        fill="#3a2405"
      >
        A
      </text>
    </svg>
  );
}
