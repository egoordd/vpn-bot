import type { Metadata } from "next";

import { SiteFooter } from "@/components/nav/SiteFooter";
import { SiteNav } from "@/components/nav/SiteNav";
import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";
import "./download.css";

export const metadata: Metadata = {
  title: "Как установить Happ",
  description:
    "Где скачать приложение Happ для iPhone, Android, Windows, macOS и Linux: прямые ссылки, инструкция для App Store и как отличить настоящее приложение от подделок.",
  robots: { index: true, follow: true },
};

/** Verified against the official happ.info download dialog on 6 August 2026. */
const LINKS = {
  androidPlay: "https://play.google.com/store/apps/details?id=com.happproxy",
  androidApk: "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk",
  windows: "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe",
  macDmg: "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.macOS.universal.dmg",
  iosGlobal: "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215",
  linuxDeb: "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.deb",
  linuxRpm: "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.rpm",
  linuxPkg:
    "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.pkg.tar.zst",
  official: "https://happ.info/",
};

interface Action {
  label: string;
  href: string;
  primary?: boolean;
}

interface Platform {
  tag: string;
  title: string;
  actions: Action[];
  hint: string;
}

/** Everything except iPhone, where the store account decides and a card cannot
 *  carry the answer. That case gets its own section below. */
const PLATFORMS: Platform[] = [
  {
    tag: "Android",
    title: "Магазин или файл",
    actions: [
      { label: "Google Play", href: LINKS.androidPlay, primary: true },
      { label: "Скачать APK", href: LINKS.androidApk },
    ],
    hint: "Если Google Play не открывается или просит другой аккаунт, берите APK. Это тот же официальный файл, просто ставится мимо магазина: откройте его и разрешите установку.",
  },
  {
    tag: "Windows",
    title: "Обычный установщик",
    actions: [{ label: "Скачать для Windows", href: LINKS.windows, primary: true }],
    hint: "Магазин не нужен, файл запускается как любая другая программа.",
  },
  {
    tag: "macOS",
    title: "Лучше через .dmg",
    actions: [
      { label: "Скачать .dmg", href: LINKS.macDmg, primary: true },
      { label: "App Store", href: LINKS.iosGlobal },
    ],
    hint: "На Mac проще всего .dmg: он не зависит от страны вашего Apple ID. Откройте файл и перетащите Happ в «Программы». App Store сработает только на нероссийском аккаунте.",
  },
  {
    tag: "Linux",
    title: "Пакет под ваш дистрибутив",
    actions: [
      { label: ".deb", href: LINKS.linuxDeb },
      { label: ".rpm", href: LINKS.linuxRpm },
      { label: ".pkg", href: LINKS.linuxPkg },
    ],
    hint: "deb для Debian и Ubuntu, rpm для Fedora и RHEL, pkg для Arch.",
  },
];

const STORE_STEPS = [
  <>
    «Настройки», нажмите своё имя вверху, <b>«Контент и покупки»</b>.
  </>,
  <>
    «Просмотреть», войдите, если попросит, затем <b>«Страна/регион»</b>.
  </>,
  <>«Изменить страну или регион», выберите страну, где приложение есть. Удобнее всего Германия.</>,
  <>
    В способах оплаты выберите <b>«Нет»</b>. Никакую карту вводить не надо.
  </>,
  <>
    Адрес, индекс и телефон заполните любыми. Важен только формат страны: для Германии это индекс
    из пяти цифр, например 10115, и номер, начинающийся с +49.
  </>,
  <>
    Откройте <a href={LINKS.iosGlobal}>страницу Happ в App Store</a> и установите.
  </>,
  <>После установки регион можно вернуть на российский. Приложение останется и будет работать.</>,
];

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
            <span className="eyebrow">Установка</span>
            <h1 className="dl__title">Как установить Happ</h1>
            <p className="lead dl__lead">
              В Happ добавляется ваша ссылка-подписка, и внутри сразу все страны и протоколы.
              Ниже официальные ссылки по системам. На Android, Windows, macOS и Linux установка
              занимает минуту. С iPhone сложнее, и дело не в самом приложении: там всё упирается
              в страну вашего Apple&nbsp;ID.
            </p>
          </header>

          <section className="dl__warn" aria-labelledby="appstore">
            <Pill tone="warn">iPhone и iPad</Pill>
            <h2 id="appstore" className="dl__warn-title">
              Happ в App Store виден не всем
            </h2>
            <p>
              Появится приложение в магазине или нет, зависит от одного — <b>какая страна указана
              в вашем Apple&nbsp;ID</b>. Если российская, Happ там не показывается. Само приложение
              работает и обновляется, дело только в витрине магазина.
            </p>
            <p className="dl__warn-check">
              Решается сменой страны App Store — это обычная настройка аккаунта, занимает пару минут
              и в любой момент отменяется. Как именно — расписано ниже.
            </p>
          </section>

          <section className="dl__grid" aria-label="Установка по системам">
            {PLATFORMS.map((platform) => (
              <article key={platform.tag} className="dl__card">
                <span className="dl__card-tag mono">{platform.tag}</span>
                <h2 className="dl__card-title">{platform.title}</h2>
                <div className="dl__actions">
                  {platform.actions.map((action) => (
                    <Button
                      key={action.label}
                      href={action.href}
                      variant={action.primary ? "primary" : "ghost"}
                    >
                      {action.label}
                    </Button>
                  ))}
                </div>
                <p className="dl__hint">{platform.hint}</p>
              </article>
            ))}
          </section>

          <section className="dl__iphone" aria-labelledby="iphone">
            <header className="dl__iphone-head">
              <span className="eyebrow">Отдельный случай</span>
              <h2 id="iphone" className="dl__iphone-title">
                iPhone и iPad
              </h2>
              <p className="dl__iphone-lead">
                На iPhone приложение ставится только из App Store, других способов iOS не даёт.
                Поэтому всё упирается в одно: из какой витрины магазина качает ваш аккаунт. С
                самим Happ ничего не случилось. Он работает и обновляется, просто в российской
                витрине его больше нет: Apple убирает оттуда такие программы.
              </p>
            </header>

            <div className="dl__case">
              <h3 className="dl__case-title">Если Apple ID не российский</h3>
              <p>Ставьте как обычно, ничего делать не нужно.</p>
              <div className="dl__actions">
                <Button href={LINKS.iosGlobal}>Открыть в App Store</Button>
              </div>
            </div>

            <div className="dl__case">
              <h3 className="dl__case-title">Если Apple ID российский</h3>
              <p>
                Отдельная российская сборка <b>Happ Proxy Utility Plus</b> раньше существовала, но
                её убрали из App Store — сейчас она не открывается ни с какого аккаунта. Остаётся
                один рабочий путь: сменить страну магазина, это делается за пару минут и обратимо.
              </p>
            </div>

            <div className="dl__case dl__case--steps">
              <h3 className="dl__case-title">Как сменить страну App Store</h3>
              <p>
                У аккаунта Apple есть страна магазина, и её разрешено менять, это обычная
                настройка. Фотографии, контакты и всё остальное в iCloud остаются на месте.
                Меняются только магазин и платёжные данные. Карту привязывать не нужно: в
                способах оплаты есть вариант «Нет».
              </p>
              <p className="dl__note">
                Одна оговорка, из-за которой чаще всего ничего не выходит. Пока на балансе
                аккаунта лежат деньги или действуют подписки, оформленные через App Store, Apple
                смену страны не пропустит: кнопка просто не сработает. Сначала потратьте баланс и
                отмените подписки. «Семейный доступ» тоже иногда мешает.
              </p>
              <ol className="dl__steps">
                {STORE_STEPS.map((step, index) => (
                  <li key={index} className="dl__step">
                    <span className="dl__step-n mono">{String(index + 1).padStart(2, "0")}</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
              <p className="dl__hint">
                Единственное, чего не будет после возврата, это обновлений: пока регион
                российский, App Store не увидит приложение. Понадобится обновить, переключитесь на
                Германию ещё раз, тем же способом.
              </p>
              <p className="dl__hint">
                Если варианта «Нет» в способах оплаты не появилось, значит что-то из оговорки выше
                не выполнено: остался баланс или активная подписка. Второй путь, его предлагает
                сама Apple, это завести <b>отдельный Apple&nbsp;ID</b> с нужной страной и входить
                под ним только в App Store, оставив основной аккаунт для iCloud.
              </p>
            </div>
          </section>

          <section className="dl__next">
            <h2 className="dl__next-title">Приложение установлено, что дальше</h2>
            <p>
              Откройте <a href="/connect">страницу подключения</a>: там ваша ссылка-подписка и
              кнопка, которая добавляет её в Happ автоматически. Останется нажать «Подключить».
            </p>
            <div className="dl__actions">
              <Button href="/connect" size="lg">
                Перейти к подключению
              </Button>
              <Button href="https://t.me/unlock_support_bot" variant="ghost" size="lg">
                Написать в поддержку
              </Button>
            </div>
            <p className="dl__hint">
              Все ссылки на этой странице ведут в официальный магазин или в репозиторий
              разработчика,{" "}
              <a href={LINKS.official} target="_blank" rel="noreferrer">
                happ.info
              </a>
              . Своих сборок приложения мы не раздаём. Если возиться не хочется, напишите в
              поддержку: проведём по шагам или подберём другое приложение под ваш случай.
            </p>
          </section>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
