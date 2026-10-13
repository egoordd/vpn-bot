import { Button } from "@/components/ui/Button";
import { botLink } from "@/lib/site";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import { BoardingPass } from "./BoardingPass";
import "./hero.css";

/** Первый экран: небо, облака, маршрут самолёта и посадочный талон в свободный интернет. */
export function BoardingHero() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero__sky" aria-hidden>
        <span className="cloud cloud--1" />
        <span className="cloud cloud--2" />
        <span className="cloud cloud--3" />
        <svg className="hero__route" viewBox="0 0 1200 520" preserveAspectRatio="none">
          <path id="route" d="M-20 470 C 260 420, 420 120, 720 150 S 1100 60, 1240 40" />
          <g className="hero__plane">
            <path d="M0 -5 L14 0 L0 5 L3 0 Z" />
            <animateMotion dur="14s" repeatCount="indefinite" rotate="auto">
              <mpath href="#route" />
            </animateMotion>
          </g>
        </svg>
      </div>

      <div className="container hero__grid">
        <div className="hero__copy">
          <p className="hero__status">
            <span className="hero__status-dot" aria-hidden /> Посадка открыта · {TRIAL_DAYS_LABEL} бесплатно
          </p>
          <h1 id="hero-title" className="hero__title">
            Ваш билет в <span>свободный интернет</span>
          </h1>
          <p className="lead hero__lead">
            Etalon — VPN первого класса: быстрые серверы в четырёх странах, автопилот сам выбирает лучший
            маршрут, а российские сервисы работают без пересадок.
          </p>
          <div className="hero__actions">
            <Button href={botLink()}>Получить билет — {TRIAL_DAYS_LABEL} бесплатно</Button>
            <Button href="#tickets" variant="ghost">
              Цены на билеты
            </Button>
          </div>
        </div>
        <BoardingPass />
      </div>
    </section>
  );
}
