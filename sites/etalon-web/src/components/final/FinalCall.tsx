import { Button } from "@/components/ui/Button";
import { LogoMark } from "@/components/ui/LogoMark";
import { botLink } from "@/lib/site";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import "./final.css";

export function FinalCall() {
  return (
    <section className="final" aria-labelledby="final-title">
      <div className="container">
        <div className="final__card reveal">
          <LogoMark className="final__key" />
          <div className="final__text">
            <span className="final__tag">Посадка открыта</span>
            <h2 id="final-title">Свободный интернет ждёт на борту</h2>
            <p>{TRIAL_DAYS_LABEL} бесплатно, до 2 устройств, без оплаты.</p>
          </div>
          <Button href={botLink()} variant="gold">
            Получить билет
          </Button>
        </div>
      </div>
    </section>
  );
}
