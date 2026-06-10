import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";
import { botLink } from "@/lib/site";
import { HeroTunnel } from "./HeroTunnel";
import "./hero.css";

export function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-heading">
      <HeroTunnel />

      <div className="container hero__inner">
        <div className="hero__copy">
          <Pill tone="accent" live>
            Reality · обходит DPI операторов
          </Pill>

          <h1 id="hero-heading" className="hero__title">
            Интернет без границ.
            <br />
            Трафик, которого
            <span className="hero__title-accent"> не видно</span>.
          </h1>

          <p className="lead hero__lead">
            UnLock прячет ваше соединение под обычный HTTPS, поэтому операторы и
            фильтры РКН не отличают его от захода на сайт. Подключение — по
            ссылке-подписке, которая обновляется сама.
          </p>

          <div className="hero__actions">
            <Button href={botLink()} size="lg">
              Подключить за минуту
            </Button>
            <Button href="#pricing" variant="ghost" size="lg">
              Смотреть тарифы
            </Button>
          </div>

          <ul className="hero__points">
            <li>
              <CheckIcon /> Пробник на 7 дней без карты
            </li>
            <li>
              <CheckIcon /> Оплата картой РФ и криптой
            </li>
            <li>
              <CheckIcon /> Доступ без VPN — чистый домен
            </li>
          </ul>
        </div>

        <aside className="hero__panel" aria-label="Состояние соединения">
          <div className="hero__panel-head">
            <span className="mono hero__panel-label">tunnel://unlock</span>
            <Pill tone="accent" live>
              активно
            </Pill>
          </div>
          <dl className="hero__stats">
            <div>
              <dt>Протокол</dt>
              <dd className="mono">VLESS · Reality</dd>
            </div>
            <div>
              <dt>Маскировка</dt>
              <dd className="mono">TLS 1.3 · self-steal</dd>
            </div>
            <div>
              <dt>Отпечаток</dt>
              <dd className="mono">firefox</dd>
            </div>
            <div>
              <dt>Видимость для DPI</dt>
              <dd className="hero__stat-accent mono">обычный сайт</dd>
            </div>
          </dl>
        </aside>
      </div>
    </section>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" aria-hidden>
      <path d="m3 8.5 3 3 7-7.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
