export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export const STORAGE_KEYS = {
  token: "auth_token",
  user: "auth_user",
  // Round 2 fix (Stream C D3): the selected modality is persisted like
  // the token/user, so courses under another modality do not look
  // vanished after logout/login or refresh.
  selectedSchool: "selected_school",
};
