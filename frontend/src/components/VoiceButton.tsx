import { useRef, useState } from "react";
import { Loader2, Mic, Square } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { blobToWav } from "../lib/wav";
import { cx } from "./ui";

const supported = typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
const MAX_MS = 60_000;

/** Record -> 16 kHz WAV -> Muse Voice Transcribe. Hides itself when the backend says AI is unavailable. */
export function VoiceButton({ onText }: { onText: (text: string) => void }) {
  const [state, setState] = useState<"idle" | "recording" | "working" | "unavailable">("idle");
  const [note, setNote] = useState("");
  const rec = useRef<MediaRecorder | null>(null);

  if (!supported || state === "unavailable") return null;

  const start = async () => {
    setNote("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const r = new MediaRecorder(stream);
      r.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      r.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setState("working");
        try {
          const wav = await blobToWav(new Blob(chunks, { type: r.mimeType }));
          const { text } = await api.transcribe(wav);
          if (text.trim()) onText(text.trim());
          else setNote("Didn't catch that. Try again a little closer to the mic.");
          setState("idle");
        } catch (e) {
          if (e instanceof ApiError && e.status === 503) { setState("unavailable"); return; }
          setNote(e instanceof ApiError && e.status === 413 ? "That recording is too long. Keep it under a minute." : "Couldn't transcribe that. You can type your goal instead.");
          setState("idle");
        }
      };
      rec.current = r;
      r.start();
      setState("recording");
      setTimeout(() => r.state === "recording" && r.stop(), MAX_MS);
    } catch {
      setNote("Microphone access was blocked. You can type your goal instead.");
    }
  };

  const label = state === "recording" ? "Stop recording" : state === "working" ? "Transcribing" : "Speak your goal";
  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" onClick={state === "recording" ? () => rec.current?.stop() : start} disabled={state === "working"}
        aria-label={label} title={label}
        className={cx("press grid size-11 place-items-center rounded-full border transition-colors",
          state === "recording" ? "border-rose bg-rose text-white" : "border-line bg-surface text-ink hover:border-control")}>
        {state === "working" ? <Loader2 className="size-5 animate-spin" aria-hidden />
          : state === "recording" ? <Square className="size-4 fill-current" aria-hidden /> : <Mic className="size-5" aria-hidden />}
      </button>
      <span className="text-[13px] text-muted" aria-live="polite">{state === "recording" ? "Listening… tap to stop" : state === "working" ? "Transcribing with Muse…" : note || "Or say it out loud"}</span>
    </span>
  );
}
