import type { Metadata } from "next";

import { SiteFooter } from "@/components/nav/SiteFooter";
import { SiteNav } from "@/components/nav/SiteNav";
import "./download.css";

export const metadata: Metadata = {
  title: "Как установить Happ",
  description:
    "Где скачать приложение Happ для iPhone, Android, Windows, macOS и Linux — прямые ссылки и как отличить настоящее приложение от подделок.",
  robots: { index: true, follow: true },
};

/** Verified against the official happ.info download dialog on 6 August 2026. */
const LINKS = {
  androidPlay: "https://play.google.com/store/apps/details?id=com.happproxy",
  androidApk: "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk",
  windows: "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe",
  macDmg: "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.macOS.universal.dmg",
  macStore: "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215",
  iosGlobal: "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215",
  iosRu: "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6788279553",
  linuxDeb: "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.deb",
  linuxRpm: "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.rpm",
  linuxPkg:
    "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.pkg.tar.zst",
  official: "https://happ.info/",
};

export default function DownloadPage() {
  return (
    <>
      <SiteNav />
      <main id="main" className="dl">
        <div className="container dl__inner">
          <a href="/" className="dl__back">
            ← На главную
          </a>

          <header className="dl__head">
            <h1 className="dl__title">Как установить Happ</h1>
            <p className="dl__lead">
              Happ — приложение, в которое добавляется ваша ссылка-подписка. Ниже прямые ссылки
              для каждой системы. На Android и компьютерах всё ставится в один клик; с iPhone
              сейчас сложнее, и об этом честно написано ниже.
            </p>
          </header>

          <section className="dl__warn" aria-labelledby="fakes">
            <h2 id="fakes" className="dl__warn-title">
              Сначала главное: в поиске App Store настоящего Happ нет
            </h2>
            <p>
              Если искать «Happ» в российском App Store, находятся <b>«Happ VPN»</b> и{" "}
              <b>«Happ VPN&nbsp;++»</b>. Это не Happ. Мы проверили издателей — у этих приложений
              другие разработчики и другие идентификаторы, они просто используют похожее название.
              Ставить их не нужно.
            </p>
            <p className="dl__warn-check">
              Настоящее приложение всегда издано <b>Flyfrog LLC</b>. Это видно на странице
              приложения в разделе «Разработчик». Если там другое имя — это не Happ.
            </p>
          </section>

          <section className="dl__plat">
            <h2 className="dl__plat-title">
              <span className="dl__plat-icon" aria-hidden="true">
                🤖
              </span>
              Android
            </h2>
            <p className="dl__plat-note">Самый простой случай — работает без оговорок.</p>
            <div className="dl__actions">
              <a className="dl__btn dl__btn--primary" href={LINKS.androidPlay} target="_blank" rel="noreferrer">
                Google Play
              </a>
              <a className="dl__btn" href={LINKS.androidApk} target="_blank" rel="noreferrer">
                Скачать APK напрямую
              </a>
            </div>
            <p className="dl__hint">
              Если Google Play не открывается или требует другой аккаунт — берите APK. Это тот же
              официальный файл, просто ставится мимо магазина: откройте скачанный файл и
              разрешите установку.
            </p>
          </section>

          <section className="dl__plat">
            <h2 className="dl__plat-title">
              <span className="dl__plat-icon" aria-hidden="true">
                🪟
              </span>
              Windows
            </h2>
            <div className="dl__actions">
              <a className="dl__btn dl__btn--primary" href={LINKS.windows} target="_blank" rel="noreferrer">
                Скачать установщик
              </a>
            </div>
            <p className="dl__hint">Обычный установщик, магазин не нужен.</p>
          </section>

          <section className="dl__plat">
            <h2 className="dl__plat-title">
              <span className="dl__plat-icon" aria-hidden="true">
                🍎
              </span>
              macOS
            </h2>
            <div className="dl__actions">
              <a className="dl__btn dl__btn--primary" href={LINKS.macDmg} target="_blank" rel="noreferrer">
                Скачать .dmg
              </a>
              <a className="dl__btn" href={LINKS.macStore} target="_blank" rel="noreferrer">
                App Store (не для российских аккаунтов)
              </a>
            </div>
            <p className="dl__hint">
              На Mac проще всего .dmg — он не зависит от страны вашего Apple&nbsp;ID. Откройте файл
              и перетащите Happ в «Программы».
            </p>
          </section>

          <section className="dl__plat">
            <h2 className="dl__plat-title">
              <span className="dl__plat-icon" aria-hidden="true">
                🐧
              </span>
              Linux
            </h2>
            <div className="dl__actions">
              <a className="dl__btn" href={LINKS.linuxDeb} target="_blank" rel="noreferrer">
                .deb — Debian, Ubuntu
              </a>
              <a className="dl__btn" href={LINKS.linuxRpm} target="_blank" rel="noreferrer">
                .rpm — Fedora, RHEL
              </a>
              <a className="dl__btn" href={LINKS.linuxPkg} target="_blank" rel="noreferrer">
                .pkg — Arch
              </a>
            </div>
          </section>

          <section className="dl__plat dl__plat--hard">
            <h2 className="dl__plat-title">
              <span className="dl__plat-icon" aria-hidden="true">
                📱
              </span>
              iPhone и iPad
            </h2>
            <p className="dl__plat-note">
              Здесь честно: это единственная система, где всё зависит от страны вашего
              Apple&nbsp;ID, и обойти это нельзя — на iPhone приложения ставятся только из App
              Store.
            </p>

            <div className="dl__case">
              <h3>Если Apple ID не российский</h3>
              <p>Ставится обычным способом, ничего делать не нужно.</p>
              <div className="dl__actions">
                <a className="dl__btn dl__btn--primary" href={LINKS.iosGlobal} target="_blank" rel="noreferrer">
                  Открыть в App Store
                </a>
              </div>
            </div>

            <div className="dl__case">
              <h3>Если Apple ID российский</h3>
              <p>
                В российской витрине App Store обычного Happ сейчас нет. У разработчика есть
                отдельная версия для России — <b>Happ Proxy Utility Plus</b>. Она не находится
                поиском, открывается только по прямой ссылке и не у всех аккаунтов:
              </p>
              <div className="dl__actions">
                <a className="dl__btn" href={LINKS.iosRu} target="_blank" rel="noreferrer">
                  Российская версия
                </a>
              </div>
              <p className="dl__hint">
                Если ссылка не открывается или App Store пишет, что приложение недоступно —
                значит, для вашего аккаунта эта версия закрыта. Тогда на iPhone остаётся один
                путь: аккаунт App Store другой страны. Ничего другого iOS не позволяет, и любые
                «Happ» из поиска — чужие приложения, а не обход этого ограничения.
              </p>
            </div>

            <p className="dl__hint">
              Если возиться не хочется — напишите в поддержку, подберём рабочий вариант под ваше
              устройство.
            </p>
          </section>

          <section className="dl__next">
            <h2>Приложение установлено — что дальше</h2>
            <p>
              Откройте <a href="/connect">страницу подключения</a>: там ваша ссылка-подписка и
              кнопка, которая добавляет её в Happ автоматически. Дальше останется нажать
              «Подключить».
            </p>
            <p className="dl__hint">
              Все ссылки на этой странице ведут в официальный магазин или в репозиторий
              разработчика — <a href={LINKS.official} target="_blank" rel="noreferrer">happ.info</a>.
              Мы не раздаём собственные сборки приложения.
            </p>
          </section>

          <footer className="dl__foot">
            <p>
              Не получается установить? Поддержка —{" "}
              <a href="https://t.me/unlock_support_bot" target="_blank" rel="noreferrer">
                @unlock_support_bot
              </a>
              , отвечаем и помогаем довести до рабочего состояния.
            </p>
          </footer>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
