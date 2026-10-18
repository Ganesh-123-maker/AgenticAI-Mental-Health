/**
 * Format a message created_at timestamp like "Today, 6:32 PM".
 * Returns null when the value is missing or unparseable (caller hides it).
 */
export function formatMessageTime(createdAt) {
  if (!createdAt) return null;
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return null;

  const timePart = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  if (sameDay) return `Today, ${timePart}`;
  return `${date.toLocaleDateString([], { month: "short", day: "numeric" })}, ${timePart}`;
}

/** "Good morning/afternoon/evening. I'm here to listen." based on local time. */
export function timeOfDayGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning. I'm here to listen.";
  if (hour < 18) return "Good afternoon. I'm here to listen.";
  return "Good evening. I'm here to listen.";
}
