"use client";

import { useState } from "react";

export function AdminLogin() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(false);
    const res = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    setLoading(false);
    if (res.ok) {
      window.location.reload();
    } else {
      setError(true);
    }
  }

  return (
    <main className="admin admin--login">
      <form className="admin-login" onSubmit={onSubmit}>
        <h1>Админ-панель</h1>
        <p>Введите пароль для доступа к статистике.</p>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Пароль"
          autoFocus
        />
        {error && <span className="admin-login__error">Неверный пароль</span>}
        <button type="submit" disabled={loading || !password}>
          {loading ? "Вход…" : "Войти"}
        </button>
      </form>
    </main>
  );
}
