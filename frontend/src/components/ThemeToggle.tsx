import { Moon, Sun } from "lucide-react";
import { useTheme } from "../lib/theme";
import { cx } from "./ui";

/** Switches between light and dark (starts from the system setting until the person picks one). */
export function ThemeToggle({ label = false }: { label?: boolean }) {
  const [, setTheme, mode] = useTheme();
  const dark = mode === "dark";
  return (
    <button type="button" onClick={() => setTheme(dark ? "light" : "dark")} aria-pressed={dark}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className={cx("press flex min-h-11 items-center gap-3 rounded-2xl text-[15px] text-ink/85 hover:bg-raised", label ? "w-full px-2" : "size-11 justify-center rounded-full")}>
      <span className={cx("grid size-9 place-items-center rounded-xl", label ? "bg-raised" : "")}>
        {dark ? <Sun className="size-[19px]" strokeWidth={1.9} aria-hidden /> : <Moon className="size-[19px]" strokeWidth={1.9} aria-hidden />}
      </span>
      {label && <span className="hidden lg:inline">{dark ? "Light mode" : "Dark mode"}</span>}
    </button>
  );
}
