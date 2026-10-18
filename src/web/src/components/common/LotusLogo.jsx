/**
 * Stylized lotus mark used for the PsychAgent brand.
 * Accepts className for sizing/color via currentColor.
 */
export function LotusLogo({ className = "h-6 w-6" }) {
  return (
    <svg viewBox="0 0 48 48" fill="none" className={className} aria-hidden="true">
      <circle cx="24" cy="24" r="22.5" stroke="currentColor" strokeWidth="2.5" />
      <path
        d="M24 12c2.6 3.2 3.9 6.6 3.9 10.2 0 4.5-1.7 8-3.9 10.3-2.2-2.3-3.9-5.8-3.9-10.3 0-3.6 1.3-7 3.9-10.2Z"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path
        d="M13.5 19.5c3.9.6 7 2.3 9.2 5.2 2.3 3 3.2 6.3 2.8 9.8-3.6-.6-6.9-2.3-9.2-5.2-2.2-3-3.1-6.3-2.8-9.8Z"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path
        d="M34.5 19.5c-3.9.6-7 2.3-9.2 5.2-2.3 3-3.2 6.3-2.8 9.8 3.6-.6 6.9-2.3 9.2-5.2 2.2-3 3.1-6.3 2.8-9.8Z"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path
        d="M14 33.5c3.3 2.2 6.6 3.3 10 3.3s6.7-1.1 10-3.3"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  );
}
