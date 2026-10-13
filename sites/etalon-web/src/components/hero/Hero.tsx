import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";
import { botLink } from "@/lib/site";
import { HeroKey } from "./HeroKey";
import "./hero.css";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";

export function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-heading">
      <div className="container hero__inner">
        <div className="hero__visual">
          <HeroKey />
        </div>

        <div className="hero__copy">
          <Pill tone="accent" live>
            Стабильно работает
          </Pill>

          <h1 id="hero-heading" className="hero__title">
            Эталон свободного интернета — <span className="hero__title-accent">быстро и стабильно</span>
          </h1>

          <p className="lead hero__lead">
            Один тап — и вы онлайн. Etalon сам выбирает быстрый сервер, а банки
            и Госуслуги работают без отключения VPN.
          </p>

          <div className="hero__actions">
            <Button href={botLink()} size="lg">
              Попробовать бесплатно
            </Button>
            <Button href="#pricing" variant="ghost" size="lg">
              Тарифы
            </Button>
          </div>

          <ul className="hero__points">
            <li>
              <CheckIcon /> {TRIAL_DAYS_LABEL} бесплатно в Telegram
            </li>
            <li>
              <CheckIcon /> 4 страны в одной подписке
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
