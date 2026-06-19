"use client";

import "./theme-toggle.css";

export function ThemeToggle() {
  const toggle = () => {
    const root = document.documentElement;
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* storage unavailable — theme still applies for this session */
    }
  };

  return (
    <button type="button" className="ttoggle" onClick={toggle} aria-label="Переключить тему">
      <svg className="ttoggle__moon" viewBox="0 0 20 20" width="18" height="18" fill="none" aria-hidden>
        <path
          d="M16 11.5A6.5 6.5 0 0 1 8.5 4a6.5 6.5 0 1 0 7.5 7.5Z"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
      </svg>
      <svg className="ttoggle__sun" viewBox="0 0 20 20" width="18" height="18" fill="none" aria-hidden>
        <circle cx="10" cy="10" r="3.6" stroke="currentColor" strokeWidth="1.6" />
        <path
          d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
    </button>
  );
}
