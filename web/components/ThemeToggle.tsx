"use client";

import { useEffect, useState } from "react";

type Choice = "light" | "dark" | "system";
const KEY = "sdoc-theme";

/**
 * Light, dark, or whatever the machine says.
 *
 * Three states rather than two on purpose: a two-way switch has to start
 * somewhere, and starting it wrong means a reader whose laptop is in dark
 * mode gets a white flash every morning. "System" is the default and stays
 * the default until someone actually chooses.
 *
 * The choice is per-browser and nothing is stored about it anywhere else -
 * it is a preference about this screen, not a fact about the shipments.
 */
export default function ThemeToggle() {
  const [choice, setChoice] = useState<Choice>("system");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let saved: Choice = "system";
    try {
      const v = localStorage.getItem(KEY);
      if (v === "light" || v === "dark") saved = v;
    } catch {
      // private windows and blocked site data both throw; the default holds
    }
    setChoice(saved);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const root = document.documentElement;
    if (choice === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", choice);
    try {
      if (choice === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, choice);
    } catch {
      // the page still looks right for this visit; only the memory is lost
    }
  }, [choice, ready]);

  const options: { value: Choice; label: string; icon: string }[] = [
    { value: "light", label: "Light", icon: "☀" },
    { value: "dark", label: "Dark", icon: "☾" },
    { value: "system", label: "System", icon: "◐" },
  ];

  return (
    <div className="theme" role="group" aria-label="Colour theme">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => setChoice(o.value)}
          aria-pressed={ready && choice === o.value}
          title={`${o.label} theme`}
        >
          <span aria-hidden="true">{o.icon}</span>
          <span className="sr-only">{o.label} theme</span>
        </button>
      ))}
    </div>
  );
}
