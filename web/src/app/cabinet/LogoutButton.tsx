"use client";

export function LogoutButton() {
  async function logout() {
    try {
      await fetch("/api/auth/telegram", { method: "DELETE" });
    } finally {
      window.location.reload();
    }
  }

  return (
    <button type="button" className="cab__logout mono" onClick={() => void logout()}>
      Выйти
    </button>
  );
}
