"use client";

import { useEffect, useState } from "react";

import "./cookie-banner.css";

const STORAGE_KEY = "unlock-cookie-consent";
type Consent = "accepted" | "rejected";

export function CookieBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved !== "accepted" && saved !== "rejected") setVisible(true);
    } catch {
      setVisible(true);
    }
  }, []);

  const choose = (consent: Consent) => {
    try {
      localStorage.setItem(STORAGE_KEY, consent);
    } catch {
      /* private mode / storage disabled — just dismiss for this visit */
    }
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      className="cookie"
      role="dialog"
      aria-live="polite"
      aria-label="Согласие на использование cookie"
    >
      <div className="cookie__inner">
        <p className="cookie__text">
          Мы используем cookie, чтобы сайт работал корректно и запоминал ваши
          настройки. Сторонние аналитику и рекламные трекеры не подключаем.
          Подробнее — в{" "}
          <a href="/privacy" className="cookie__link">
            политике конфиденциальности
          </a>
          .
        </p>
        <div className="cookie__actions">
          <button
            type="button"
            className="cookie__btn cookie__btn--ghost"
            onClick={() => choose("rejected")}
          >
            Отклонить
          </button>
          <button
            type="button"
            className="cookie__btn cookie__btn--solid"
            onClick={() => choose("accepted")}
          >
            Принять
          </button>
        </div>
      </div>
    </div>
  );
}
