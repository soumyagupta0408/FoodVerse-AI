export const splitList = (s: string | undefined | null): string[] => (s ?? "").split(/[,\n]/).map((x) => x.trim()).filter(Boolean);
export const joinList = (l: string[] | undefined | null) => (l ?? []).join(", ");
