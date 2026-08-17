"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Animated sun/moon dark‑mode toggle.
 *
 * Persists preference to localStorage and falls back to
 * the system `prefers-color-scheme` media query.
 * Toggles the `.dark` class on `<html>` so every CSS
 * variable resolves from the dark palette automatically.
 */
export default function ThemeToggle() {
  const [dark, setDark] = useState(false);
  /* `true` after first client render so we skip the icon
     flash when the server‑rendered HTML arrives as light. */
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    const prefersDark =
      stored === "dark" ||
      (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches);
    setDark(prefersDark);
    if (prefersDark) document.documentElement.classList.add("dark");
    setMounted(true);
  }, []);

  const toggle = useCallback(() => {
    setDark((prev) => {
      const next = !prev;
      document.documentElement.classList.toggle("dark", next);
      localStorage.setItem("theme", next ? "dark" : "light");
      return next;
    });
  }, []);

  /* Render a blank spacer until hydrated to avoid icon flash */
  if (!mounted) return <div className="w-9 h-9" />;

  return (
    <button
      id="theme-toggle"
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className="
        relative w-9 h-9 rounded-lg grid place-items-center
        text-ink-2 hover:text-accent hover:bg-accent-weak/60
        active:scale-95
        transition-all duration-200
      "
    >
      {/* Sun icon */}
      <svg
        viewBox="0 0 24 24"
        width={18}
        height={18}
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={`absolute transition-all duration-300 ${
          dark
            ? "opacity-0 rotate-90 scale-0"
            : "opacity-100 rotate-0 scale-100"
        }`}
      >
        <circle cx="12" cy="12" r="5" />
        <line x1="12" y1="1" x2="12" y2="3" />
        <line x1="12" y1="21" x2="12" y2="23" />
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
        <line x1="1" y1="12" x2="3" y2="12" />
        <line x1="21" y1="12" x2="23" y2="12" />
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
      </svg>

      {/* Moon icon */}
      <svg
        viewBox="0 0 24 24"
        width={18}
        height={18}
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={`absolute transition-all duration-300 ${
          dark
            ? "opacity-100 rotate-0 scale-100"
            : "opacity-0 -rotate-90 scale-0"
        }`}
      >
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    </button>
  );
}
