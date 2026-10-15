import { TOWERS, botLink } from "@/lib/site";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import { Tower } from "../ui/Tower";
import { Button, Rule } from "../ui/ui";
import "./hero.css";

export function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="wrap hero__inner">
        <div className="hero__emblem" aria-hidden="true">
          <span className="hero__halo" />
          <span className="hero__light" />
          <Tower className="hero__tower" />
        </div>
        <p className="hero__word display" aria-hidden="true">
          Avangard
        </p>
        <Rule>VPN</Rule>
        <h1 id="hero-title" className="hero__title">
          Ваша крепость в интернете
        </h1>
        <p className="hero__lead">
          Защищённое соединение через Германию и Нидерланды. Авто-выбор сам держит самый быстрый сервер, а бот
          говорит на пяти языках.
        </p>
        <div className="hero__actions">
          <Button href={botLink("site")} size="lg" external>
            Открыть ворота — {TRIAL_DAYS_LABEL} бесплатно
          </Button>
          <Button href="/#pricing" variant="outline" size="lg">
            Тарифы
          </Button>
        </div>
        <ul className="hero__trust">
          <li>{TOWERS.map((t) => t.flag).join(" ")} две страны</li>
          <li>до 5 устройств</li>
          <li>без карты на пробный период</li>
        </ul>
      </div>
    </section>
  );
}
