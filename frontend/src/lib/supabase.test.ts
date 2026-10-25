import { afterEach, describe, expect, it, vi } from "vitest";
import { signIn, signUp, SupabaseAuthError } from "./supabase";

const cfg = { url: "https://abcd.supabase.co", anonKey: "anon" };
const reply = (status: number, body: unknown) => vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));

afterEach(() => vi.unstubAllGlobals());

describe("Supabase Auth client", () => {
  it("signs up and returns a token, or null when email confirmation is required", async () => {
    const fetch = reply(200, { access_token: "tok", user: {} });
    vi.stubGlobal("fetch", fetch);
    expect(await signUp(cfg, "a@b.co", "long-password", "Riley")).toBe("tok");
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("https://abcd.supabase.co/auth/v1/signup");
    expect(init.headers.apikey).toBe("anon");
    expect(JSON.parse(init.body)).toEqual({ email: "a@b.co", password: "long-password", data: { display_name: "Riley" } });
    vi.stubGlobal("fetch", reply(200, { id: "u1", confirmation_sent_at: "now" }));
    expect(await signUp(cfg, "a@b.co", "long-password", "Riley")).toBeNull();
  });
  it("signs in with a password and turns Supabase errors into plain words", async () => {
    vi.stubGlobal("fetch", reply(200, { access_token: "tok2" }));
    expect(await signIn(cfg, "a@b.co", "pw")).toBe("tok2");
    vi.stubGlobal("fetch", reply(400, { error_code: "invalid_credentials", msg: "Invalid login credentials" }));
    await expect(signIn(cfg, "a@b.co", "bad")).rejects.toThrow("Wrong email or password.");
    vi.stubGlobal("fetch", reply(400, { msg: "Email not confirmed" }));
    await expect(signIn(cfg, "a@b.co", "pw")).rejects.toBeInstanceOf(SupabaseAuthError);
  });
});
