import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";
import { botLink } from "@/lib/site";
import "./cta.css";

export function CtaBanner() {
  return (
    <section className="section cta" aria-labelledby="cta-heading">
      <div className="container">
        <div className="cta__card">
          <div className="cta__glow" aria-hidden />
          <Pill tone="accent" live>
            3 дня бесплатно
          </Pill>
          <h2 id="cta-heading" className="cta__title">
            Проверьте, как это —<br />
            когда интернет просто работает
          </h2>
          <p className="lead cta__sub">
            Запустите бота, активируйте пробный период и подключитесь за минуту. Оплата не
            нужна.
          </p>
          <div className="cta__actions">
            <Button href={botLink()} size="lg">
              Открыть бота
            </Button>
            <Button href="/cabinet" variant="ghost" size="lg">
              Войти в кабинет
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
