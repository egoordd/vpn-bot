import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";
import { botLink } from "@/lib/site";
import { ConnectionOrbit } from "./ConnectionOrbit";
import "./hero.css";

export function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-heading">
      <div className="container hero__inner">
        <div className="hero__visual">
          <ConnectionOrbit />
        </div>

        <div className="hero__copy">
          <Pill tone="accent" live>
            Стабильно работает
          </Pill>

          <h1 id="hero-heading" className="hero__title">
            Интернет без границ — <span className="hero__title-accent">просто и надёжно</span>
          </h1>

          <p className="lead hero__lead">
            Один тап — и вы онлайн. Работает на телефоне и компьютере, не тормозит
            и не обрывается. Никаких настроек.
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
              <CheckIcon /> 3 дня бесплатно
            </li>
            <li>
              <CheckIcon /> Картой или криптой
            </li>
            <li>
              <CheckIcon /> На всех устройствах
            </li>
          </ul>
        </div>
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
