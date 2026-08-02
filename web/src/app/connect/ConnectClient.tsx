"use client";

import { useEffect, useMemo, useState } from "react";

import { CopyButton } from "@/components/ui/CopyButton";
import { Pill } from "@/components/ui/Pill";

type Platform = "ios" | "android" | "windows" | "macos" | "linux";

const PLATFORMS: { id: Platform; label: string }[] = [
  { id: "ios", label: "iPhone / iPad" },
  { id: "android", label: "Android" },
  { id: "windows", label: "Windows" },
  { id: "macos", label: "macOS" },
  { id: "linux", label: "Linux" },
];

interface AppEntry {
  name: string;
  note: string;
  recommended?: boolean;
  scheme: (url: string) => string;
  store: Partial<Record<Platform, string>>;
}

// Per-platform catalog. Order = recommendation order for that platform.
const CATALOG: Record<Platform, AppEntry[]> = {
  ios: [
    {
      name: "Happ",
      note: "проще всего",
      recommended: true,
      scheme: (u) => `happ://add/${u}`,
      store: { ios: "https://apps.apple.com/app/happ-proxy-utility/id6504287215" },
    },
    {
      name: "V2RayTun",
      note: "популярный",
      scheme: (u) => `v2raytun://import/${u}`,
      store: { ios: "https://apps.apple.com/app/v2raytun/id6476628951" },
    },
    {
      name: "Streisand",
      note: "без рекламы",
      scheme: (u) => `streisand://import/${u}`,
      store: { ios: "https://apps.apple.com/app/streisand/id6450534064" },
    },
  ],
  android: [
    {
      name: "Happ",
      note: "проще всего",
      recommended: true,
      scheme: (u) => `happ://add/${u}`,
      store: { android: "https://play.google.com/store/apps/details?id=com.happproxy" },
    },
    {
      name: "V2RayTun",
      note: "популярный",
      scheme: (u) => `v2raytun://import/${u}`,
      store: { android: "https://play.google.com/store/apps/details?id=com.v2raytun.android" },
    },
    {
      name: "Hiddify",
      note: "кросс-платформенный",
      scheme: (u) => `hiddify://import/${u}`,
      store: { android: "https://play.google.com/store/apps/details?id=app.hiddify.com" },
    },
  ],
  windows: [
    {
      name: "Hiddify",
      note: "рекомендуем",
      recommended: true,
      scheme: (u) => `hiddify://import/${u}`,
      store: { windows: "https://hiddify.com/" },
    },
    {
      name: "V2RayTun",
      note: "простой",
      scheme: (u) => `v2raytun://import/${u}`,
      store: { windows: "https://v2raytun.com/" },
    },
  ],
  macos: [
    {
      name: "Happ",
      note: "проще всего",
      recommended: true,
      scheme: (u) => `happ://add/${u}`,
      store: { macos: "https://apps.apple.com/app/happ-proxy-utility/id6504287215" },
    },
    {
      name: "Streisand",
      note: "без рекламы",
      scheme: (u) => `streisand://import/${u}`,
      store: { macos: "https://apps.apple.com/app/streisand/id6450534064" },
    },
    {
      name: "Hiddify",
      note: "кросс-платформенный",
      scheme: (u) => `hiddify://import/${u}`,
      store: { macos: "https://hiddify.com/" },
    },
  ],
  linux: [
    {
      name: "Hiddify",
      note: "рекомендуем",
      recommended: true,
      scheme: (u) => `hiddify://import/${u}`,
      store: { linux: "https://hiddify.com/" },
    },
  ],
};

function detectPlatform(): Platform {
  if (typeof navigator === "undefined") return "windows";
  const ua = navigator.userAgent.toLowerCase();
  if (/iphone|ipad|ipod/.test(ua) || (ua.includes("mac") && "ontouchend" in document)) return "ios";
  if (ua.includes("android")) return "android";
  if (ua.includes("mac")) return "macos";
  if (ua.includes("linux")) return "linux";
  return "windows";
}

function readSubFromHash(): string {
  if (typeof window === "undefined") return "";
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  return (params.get("sub") ?? "").trim();
}

export function ConnectClient() {
  const [sub, setSub] = useState("");
  const [manual, setManual] = useState("");
  const [platform, setPlatform] = useState<Platform>("windows");

  useEffect(() => {
    setSub(readSubFromHash());
    setPlatform(detectPlatform());
  }, []);

  const activeSub = sub || manual.trim();
  const apps = useMemo(() => CATALOG[platform], [platform]);

  return (
    <div className="connectp__wrap">
      <header className="connectp__head">
        <Pill tone="accent">Подключение</Pill>
        <h1 className="connectp__title">Подключите VPN за 3 шага</h1>
        <p className="connectp__lead">
          Ваш доступ — одна ссылка-подписка. Импортируйте её в приложение: внутри все страны и
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
            onChange={(e) => setManual(e.target.value)}
          />
        </section>
      )}

      <div className="connectp__platforms" role="tablist" aria-label="Платформа">
        {PLATFORMS.map((p) => (
          <button
            key={p.id}
            role="tab"
            aria-selected={platform === p.id}
            className={`connectp__platform${platform === p.id ? " is-active" : ""}`}
            onClick={() => setPlatform(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <ol className="connectp__steps">
        <li className="connectp__step">
          <div className="connectp__step-head">
            <span className="connectp__step-num">1</span>
            <h2>Установите приложение</h2>
          </div>
          <p>Выберите одно из приложений ниже — рекомендованное отмечено.</p>
        </li>

        <li className="connectp__step">
          <div className="connectp__step-head">
            <span className="connectp__step-num">2</span>
            <h2>Добавьте подписку</h2>
          </div>
          <p>
            {activeSub
              ? "Нажмите «Добавить подписку» — приложение импортирует её само. Если не открылось, скопируйте ссылку выше и в приложении выберите «Добавить из буфера»."
              : "Вставьте ссылку выше — появятся кнопки «Добавить подписку»."}
          </p>
          <div className="connectp__apps">
            {apps.map((app) => (
              <div key={app.name} className={`connectp__app${app.recommended ? " is-rec" : ""}`}>
                <div className="connectp__app-info">
                  <span className="connectp__app-name">
                    {app.name}
                    {app.recommended && <span className="connectp__app-badge">рекомендуем</span>}
                  </span>
                  <span className="connectp__app-note mono">{app.note}</span>
                </div>
                <div className="connectp__app-actions">
                  {app.store[platform] && (
                    <a
                      className="connectp__app-store"
                      href={app.store[platform]}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Установить
                    </a>
                  )}
                  {activeSub && (
                    <a className="connectp__app-import" href={app.scheme(activeSub)}>
                      Добавить подписку
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
            В приложении появится список серверов. Верхний — «⚡️ Авто-обход», он сам выбирает
            рабочий сервер; ниже 🇵🇱 Польша, 🇩🇪 Германия и 🇺🇸 США. Нажмите «Подключить». Страну
            можно переключать прямо в приложении — если один сервер тормозит, выберите другой.
          </p>
        </li>
      </ol>

      <footer className="connectp__foot">
        <p className="connectp__foot-text">
          Не подключается? Напишите в поддержку —{" "}
          <a href="https://t.me/unlock_support_bot" target="_blank" rel="noreferrer">
            @unlock_support_bot
          </a>
          . Подписка и ссылка всегда доступны в <a href="/cabinet">личном кабинете</a>.
        </p>
      </footer>
    </div>
  );
}
