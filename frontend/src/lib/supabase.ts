/** Minimal Supabase Auth client (REST, no SDK): email + password sign-up and sign-in for real people.
 *  The access token is handed straight to our backend (/api/auth/supabase), which verifies it and returns an InGather
 *  session; nothing from Supabase is kept in the browser. */
export interface SupabaseConfig { url: string; anonKey: string }

export class SupabaseAuthError extends Error {
  name = "SupabaseAuthError";
}

async function call(cfg: SupabaseConfig, path: string, body: unknown): Promise<Record<string, unknown>> {
  let res: Response;
  try {
    res = await fetch(`${cfg.url}/auth/v1/${path}`, {
      method: "POST",
      headers: { apikey: cfg.anonKey, Authorization: `Bearer ${cfg.anonKey}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new SupabaseAuthError("Couldn't reach the sign-in service. Check your connection and try again.");
  }
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) throw new SupabaseAuthError(friendly(String(data.error_description ?? data.msg ?? data.message ?? data.error_code ?? "")));
  return data;
}

function friendly(msg: string): string {
  const m = msg.toLowerCase();
  if (m.includes("invalid login") || m.includes("invalid_credentials")) return "Wrong email or password.";
  if (m.includes("not confirmed")) return "Confirm your email first: open the link we sent you, then sign in.";
  if (m.includes("already registered") || m.includes("already exists")) return "An account with that email already exists. Try signing in.";
  if (m.includes("password")) return msg;
  if (m.includes("rate limit") || m.includes("too many")) return "Too many attempts. Wait a minute and try again.";
  return msg || "Sign-in failed. Try again.";
}

/** Returns an access token, or null when Supabase sent a confirmation email first. */
export async function signUp(cfg: SupabaseConfig, email: string, password: string, displayName: string): Promise<string | null> {
  const data = await call(cfg, "signup", { email, password, data: { display_name: displayName } });
  return typeof data.access_token === "string" ? data.access_token : null;
}

export async function signIn(cfg: SupabaseConfig, email: string, password: string): Promise<string> {
  const data = await call(cfg, "token?grant_type=password", { email, password });
  if (typeof data.access_token !== "string") throw new SupabaseAuthError("Sign-in failed. Try again.");
  return data.access_token;
}
