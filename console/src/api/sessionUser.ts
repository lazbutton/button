const KEY = "button-console-username";

export function rememberUsername(username: string): void {
  const value = username.trim();
  if (value) localStorage.setItem(KEY, value);
  else localStorage.removeItem(KEY);
}

export function rememberedUsername(): string | null {
  return localStorage.getItem(KEY);
}

export function forgetUsername(): void {
  localStorage.removeItem(KEY);
}
