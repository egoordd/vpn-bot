"use client";

import { useEffect, useState } from "react";

import { CopyButton } from "@/components/ui/CopyButton";
import { Pill } from "@/components/ui/Pill";

interface AppOption {
  name: string;
  note: string;
  scheme: (url: string) => string;
  store: { ios?: string; android?: string };
}

// Deep links import the subscription; store links help first-time installs.
const APPS: AppOption[] = [
  {
    name: "Happ",
    note: "рекомендуем — проще всего",
    scheme: (url) => `happ://add/${encodeURIComponent(url)}`,
    store: {
      ios: "https://apps.apple.com/app/happ-proxy-utility/id6504287215",
      android: "https://play.google.com/store/apps/details?id=com.happproxy",
    },
  },
  {
    name: "V2RayTun",
    note: "iOS / Android",
    scheme: (url) => `v2raytun://import/${encodeURIComponent(url)}`,
    store: {
      ios: "https://apps.apple.com/app/v2raytun/id6476628951",
      android: "https://play.google.com/store/apps/details?id=com.v2raytun.android",
    },
  },
  {
    name: "Hiddify",
    note: "кросс-платформенный",
    scheme: (url) => `hiddify://import/${encodeURIComponent(url)}`,
    store: {
      ios: "https://apps.apple.com/app/hiddify-proxy-vpn/id6596777532",
      android: "https://play.google.com/store/apps/details?id=app.hiddify.com",
    },
  },
];

function readSubFromHash(): string {
  if (typeof window === "undefined") return "";
  const hash = window.location.hash.replace(/^#/, "");
  const params = new URLSearchParams(hash);
  const sub = params.get("sub");
  return sub ? sub.trim() : "";
}

export function ConnectClient() {
  const [sub, setSub] = useState("");
  const [manual, setManual] = useState("");

  useEffect(() => {
    setSub(readSubFromHash());
  }, []);

  const activeSub = sub || manual.trim();

  return (
    <div className="connectp__wrap">
      <header className="connectp__head">
        <Pill tone="accent">Подключение</Pill>
        <h1 className="connectp__title">Подключите VPN за 3 шага</h1>
        <p className="connectp__lead">
          Ваш доступ — это одна ссылка-подписка. Импортируйте её в приложение: внутри все страны и
          протоколы, конфиг обновляется автоматически.
        </p>
      </header>

      {activeSub ? (
        <section className="connectp__card card">
          <span className="connectp__card-label mono">Ваша ссылка-подписка</span>
          <div className="connectp__link">
            <code className="connectp__url mono">{activeSub}</code>
            <CopyButton value={activeSub} label="Скопировать" />
          </div>
        </section>
      ) : (
        <section className="connectp__card card">
          <label className="connectp__card-label" htmlFor="sub-input">
            Вставьте ссылку-подписку (из бота или письма)
          </label>
          <input
            id="sub-input"
            className="connectp__input mono"
            placeholder="https://sub.unlockvpn.site/sub/…"
            value={manual}
            onChange={(event) => setManual(event.target.value)}
          />
        </section>
      )}

      <ol className="connectp__steps">
        <li className="connectp__step">
          <div className="connectp__step-head">
            <span className="connectp__step-num">1</span>
            <h2>Установите приложение</h2>
          </div>
          <p>Подойдёт любое из списка ниже. Если не знаете, что выбрать — ставьте Happ.</p>
        </li>

        <li className="connectp__step">
          <div className="connectp__step-head">
            <span className="connectp__step-num">2</span>
            <h2>Импортируйте подписку</h2>
          </div>
          <p>
            {activeSub
              ? "Нажмите кнопку вашего приложения — подписка добавится сама. Если не открылось, скопируйте ссылку выше и в приложении выберите «Добавить из буфера / по ссылке»."
              : "Вставьте ссылку выше, затем нажмите кнопку приложения — подписка добавится сама."}
          </p>
          <div className="connectp__apps">
            {APPS.map((app) => (
              <div key={app.name} className="connectp__app">
                <div className="connectp__app-info">
                  <span className="connectp__app-name">{app.name}</span>
                  <span className="connectp__app-note mono">{app.note}</span>
                </div>
                <div className="connectp__app-actions">
                  {activeSub && (
                    <a className="connectp__app-import" href={app.scheme(activeSub)}>
                      Импортировать
                    </a>
                  )}
                  {app.store.ios && (
                    <a className="connectp__app-store" href={app.store.ios} target="_blank" rel="noreferrer">
                      iOS
                    </a>
                  )}
                  {app.store.android && (
                    <a
                      className="connectp__app-store"
                      href={app.store.android}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Android
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </li>

        <li className="connectp__step">
          <div className="connectp__step-head">
            <span className="connectp__step-num">3</span>
            <h2>Включите и выберите страну</h2>
          </div>
          <p>
            В приложении появится список серверов (🇺🇸 США, 🇳🇱 Нидерланды, 🇵🇱 Польша). Нажмите
            «Подключить» и при желании переключайте страну прямо в приложении. Если один сервер
            тормозит — выберите другой.
          </p>
        </li>
      </ol>

      <footer className="connectp__foot">
        <p className="connectp__foot-text">
          Не подключается? Напишите в поддержку —{" "}
          <a href="https://t.me/unlock_support_bot" target="_blank" rel="noreferrer">
            @unlock_support_bot
          </a>
          . Подписка и ссылка всегда доступны в{" "}
          <a href="/cabinet">личном кабинете</a>.
        </p>
      </footer>
    </div>
  );
}
