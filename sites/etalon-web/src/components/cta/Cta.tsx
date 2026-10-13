import { Button } from "@/components/ui/Button";
import { LogoMark } from "@/components/ui/LogoMark";
import { botLink } from "@/lib/site";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import "./cta.css";

export function Cta() {
  return (
    <section className="cta" aria-labelledby="cta-title">
      <div className="container">
        <div className="cta__card reveal">
          <LogoMark className="cta__key" />
          <span className="overline cta__overline">Пробный период</span>
          <h2 id="cta-title">
            Почувствуйте <em>разницу</em>
          </h2>
          <p>{TRIAL_DAYS_LABEL} бесплатно, до 2 устройств, без оплаты и карты.</p>
          <Button href={botLink()} variant="gold">
            Получить доступ
          </Button>
        </div>
      </div>
    </section>
  );
}
