import { Button } from "@/components/ui/Button";
import { botLink } from "@/lib/site";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import { KeyArt } from "./KeyArt";
import "./hero.css";

export function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero__glow" aria-hidden />
      <div className="container hero__grid">
        <div className="hero__copy">
          <span className="overline">Etalon VPN · частная сеть</span>
          <h1 id="hero-title" className="hero__title">
            Интернет, <em>каким он должен быть</em>
          </h1>
          <p className="lead hero__lead">
            Быстрые серверы в четырёх странах, автоматический выбор маршрута и российские сервисы без
            отключения VPN. Ничего лишнего — только эталонное соединение.
          </p>
          <div className="hero__actions">
            <Button href={botLink()}>Попробовать {TRIAL_DAYS_LABEL} бесплатно</Button>
            <Button href="#pricing" variant="link">
              Тарифы от 148 ₽ в месяц
            </Button>
          </div>
        </div>

        <div className="hero__art">
          <KeyArt />
          <div className="hero__status">
            <span className="hero__status-dot" aria-hidden />
            <div>
              <strong>Соединение защищено</strong>
              <span>Авто-выбор · Нидерланды · 38 мс</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
