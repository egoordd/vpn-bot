"use client";

export function LogoutButton() {
  async function logout() {
    try {
      await fetch("/api/auth/telegram", { method: "DELETE" });
    } finally {
      window.location.reload();
    }
  }

  async function logoutEverywhere() {
    if (!window.confirm("Выйти из кабинета на всех устройствах, включая это?")) return;
    try {
      const res = await fetch("/api/auth/sign-out-everywhere", { method: "POST" });
      if (!res.ok) {
        window.alert("Не получилось. Попробуйте ещё раз через минуту.");
        return;
      }
    } catch {
      window.alert("Сеть недоступна. Попробуйте ещё раз.");
      return;
    }
    window.location.reload();
  }

  return (
    <div className="cab__logouts">
      <button type="button" className="cab__logout mono" onClick={() => void logout()}>
        Выйти
      </button>
      <button type="button" className="cab__logout mono" onClick={() => void logoutEverywhere()}>
        Выйти на всех устройствах
      </button>
    </div>
  );
}
