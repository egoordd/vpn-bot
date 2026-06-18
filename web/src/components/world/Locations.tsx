import { WorldMap } from "./WorldMap";
import "./locations.css";

const POINTS = [
  { flag: "🇺🇸", name: "США", note: "Reality · Hysteria2 · AmneziaWG" },
  { flag: "🇳🇱", name: "Нидерланды", note: "Reality · Hysteria2 · AmneziaWG" },
];

export function Locations() {
  return (
    <section className="section locations" id="locations" aria-labelledby="loc-heading">
      <div className="container">
        <div className="locations__head reveal">
          <span className="eyebrow">Сеть</span>
          <h2 id="loc-heading" className="locations__title">
            Локации, в которых вас <span className="grad-ember">не видно</span>
          </h2>
          <p className="lead locations__sub">
            Два независимых узла с обфускацией трафика. Переключайтесь прямо в
            приложении — одна подписка, все локации.
          </p>
        </div>

        <WorldMap />

        <ul className="locations__list reveal">
          {POINTS.map((p) => (
            <li key={p.name} className="locations__item">
              <span className="locations__dot" aria-hidden />
              <span className="locations__flag">{p.flag}</span>
              <span className="locations__name">{p.name}</span>
              <span className="locations__note mono">{p.note}</span>
            </li>
          ))}
          <li className="locations__item locations__item--soon">
            <span className="locations__dot locations__dot--soon" aria-hidden />
            <span className="locations__name">Новые локации</span>
            <span className="locations__note mono">скоро</span>
          </li>
        </ul>
      </div>
    </section>
  );
}
