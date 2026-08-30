import { LIVE_LOCATIONS as LIVE, SOON_LOCATIONS as SOON } from "@/lib/locations";

import { WorldMap } from "./WorldMap";
import "./locations.css";

export function Locations() {
  return (
    <section className="section locations" id="locations" aria-labelledby="loc-heading">
      <div className="container">
        <div className="locations__head reveal">
          <span className="eyebrow">Где мы есть</span>
          <h2 id="loc-heading" className="locations__title">
            Наши локации
          </h2>
          <p className="lead locations__sub">
            Серверы в разных странах. Переключайтесь в один тап — всё в одной
            подписке, новые страны добавляем.
          </p>
        </div>

        <div className="locations__panel reveal">
          <WorldMap />
        </div>

        <ul className="locations__list reveal">
          {LIVE.map((p) => (
            <li key={p.name} className="locations__item">
              <span className="locations__dot" aria-hidden />
              <span className="locations__flag">{p.flag}</span>
              <span className="locations__name">{p.name}</span>
              <span className="locations__note mono">{p.note}</span>
            </li>
          ))}
        </ul>

        <div className="locations__soon-head reveal">
          <span className="eyebrow">Скоро</span>
        </div>
        <ul className="locations__list locations__list--soon reveal">
          {SOON.map((p) => (
            <li key={p.name} className="locations__item locations__item--soon">
              <span className="locations__dot locations__dot--soon" aria-hidden />
              <span className="locations__flag">{p.flag}</span>
              <span className="locations__name">{p.name}</span>
              <span className="locations__note mono">скоро</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
