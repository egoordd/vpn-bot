import { COUNTRIES, botLink } from "@/lib/site";
import { PLANS, TRIAL_DAYS_LABEL, pricePerMonth } from "@/lib/tariffs";
import { Button, Chevron } from "../ui/ui";
import { HeroArt } from "./HeroArt";
import "./hero.css";

const CHEAPEST_MONTH = Math.min(...PLANS.map(pricePerMonth));

export function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero__dots" aria-hidden="true" />
      <div className="wrap hero__grid">
        <div className="hero__copy">
          <span className="hero__pill">
            <span className="hero__pill-dot" /> {TRIAL_DAYS_LABEL} бесплатно · без карты
          </span>
          <h1 id="hero-title">
            Интернет под&nbsp;надёжным <span className="hero__mark">щитом</span>
          </h1>
          <p className="hero__lead">
            Plata шифрует соединение и сама держит самый быстрый сервер. Банки и Госуслуги открываются, не
            выключая VPN.
          </p>
          <div className="hero__actions">
            <Button href={botLink("site")} size="lg" external>
              Попробовать {TRIAL_DAYS_LABEL} бесплатно <Chevron />
            </Button>
            <Button href="/#pricing" variant="ghost" size="lg">
              Тарифы — от {CHEAPEST_MONTH} ₽/мес
            </Button>
          </div>
          <ul className="hero__trust">
            <li>
              <span className="hero__flags">{COUNTRIES.map((c) => c.flag).join(" ")}</span> 4 страны
            </li>
            <li>до 5 устройств</li>
            <li>без автосписаний</li>
          </ul>
        </div>
        <HeroArt />
      </div>
    </section>
  );
}
