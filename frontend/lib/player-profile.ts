import { api } from "./api";

export type StoryPreference = "male" | "female";
export type PlayerProfile = {
  userId: string;
  storyPreference: StoryPreference;
  playerName: string;
  hasCompletedNameEntry: boolean;
  createdAt: string;
  updatedAt: string;
};

export function validatePlayerName(value: string): string {
  const name = value.trim();
  if (!name) throw new Error("请告诉我，你的名字。");
  if (Array.from(name).length > 12) throw new Error("名字请使用 1—12 个字符。");
  if (/[\p{Cc}\p{Cf}]/u.test(name)) throw new Error("名字中请勿使用控制字符。");
  return name;
}

// Local adapter. Replace this interface's methods when profile endpoints exist.
export const playerProfiles = {
  async currentUserId(): Promise<string> {
    try {
      const account = await api<{ email: string }>("/auth/me", { signal: AbortSignal.timeout(3000) });
      return `account:${account.email}`;
    } catch {
      let id = localStorage.getItem("galstudy.localUserId");
      if (!id) {
        id = `local:${crypto.randomUUID()}`;
        localStorage.setItem("galstudy.localUserId", id);
      }
      return id;
    }
  },
  async load(userId: string, route: StoryPreference): Promise<PlayerProfile | null> {
    const raw = localStorage.getItem(`galstudy.profile.${encodeURIComponent(userId)}.${route}`);
    if (!raw) return null;
    const data = JSON.parse(raw) as PlayerProfile;
    if (data.userId !== userId || data.storyPreference !== route ||
      typeof data.playerName !== "string" || typeof data.hasCompletedNameEntry !== "boolean" ||
      typeof data.createdAt !== "string" || typeof data.updatedAt !== "string") {
      throw new Error("本机存档无法读取，请检查浏览器存储。");
    }
    validatePlayerName(data.playerName);
    return data;
  },
  async save(userId: string, route: StoryPreference, value: string, completed: boolean): Promise<PlayerProfile> {
    const previous = await this.load(userId, route);
    const timestamp = new Date().toISOString();
    const profile: PlayerProfile = { userId, storyPreference: route, playerName: validatePlayerName(value),
      hasCompletedNameEntry: completed, createdAt: previous?.createdAt ?? timestamp, updatedAt: timestamp };
    localStorage.setItem(`galstudy.profile.${encodeURIComponent(userId)}.${route}`, JSON.stringify(profile));
    return profile;
  },
};
