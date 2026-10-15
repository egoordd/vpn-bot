import { PAY_METHODS, SITE, SUPPORT } from "@/lib/site";
import { TRIAL, TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import { ShieldMark } from "../ui/ShieldMark";
import { Button } from "../ui/ui";
import "./faq.css";

const QUESTIONS = [
  {
    q: "Как работает пробный период?",
    a: `${TRIAL_DAYS_LABEL} бесплатно, до ${TRIAL.deviceLimit} устройств и ${TRIAL.trafficGb} ГБ трафика. Карта не нужна — доступ выдаёт бот @${SITE.botUsername}. Один пробный период на аккаунт Telegram.`,
  },
  {
    q: "Как оплатить подписку?",
    a: `Выберите срок в разделе «Тарифы», укажите почту и оплатите ${PAY_METHODS} на странице платёжного сервиса. Оплата разовая — автоматических списаний нет.`,
  },
  {
    q: "Будут ли работать банки и Госуслуги?",
    a: "Да. В режиме РУ-сервисов российские сайты и приложения открываются напрямую, поэтому VPN не нужно выключать, чтобы оплатить или войти в Госуслуги.",
  },
  {
    q: "На скольких устройствах можно пользоваться?",
    a: "На любом тарифе — до 5 устройств одновременно: iPhone, iPad, Android, Windows и Mac. Подписка одна, ссылка одна.",
  },
  {
    q: "Что делать, если не подключается?",
    a: `Обновите подписку в Happ (потяните список вниз) и выберите другую страну. Не помогло — напишите в поддержку в боте, ответим в течение ${SUPPORT.replyHours} часов.`,
  },
  {
    q: "Можно ли вернуть деньги?",
    a: "Если доступ не заработал по нашей вине, напишите в поддержку в течение 24 часов после оплаты — условия в разделе 7 пользовательского соглашения.",
  },
] as const;

export function Faq() {
  return (
    <section className="section faq" id="faq" aria-labelledby="faq-title">
      <div className="wrap faq__grid">
        <div className="section-head faq__head">
          <span className="eyebrow">Вопросы</span>
          <h2 id="faq-title">Коротко о главном</h2>
          <p>Не нашли ответ — спросите поддержку прямо в боте.</p>
          <Button href={SUPPORT.botLink} variant="ghost" external>
            Написать в поддержку
          </Button>
        </div>
        <div className="faq__list">
          {QUESTIONS.map((item) => (
            <details key={item.q} className="qa">
              <summary>
                {item.q}
                <span className="qa__icon" aria-hidden="true" />
              </summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

export function Cta() {
  return (
    <section className="cta" aria-labelledby="cta-title">
      <div className="wrap">
        <div className="cta__panel">
          <ShieldMark className="cta__shield" />
          <div className="cta__copy">
            <h2 id="cta-title">Включите защиту сегодня</h2>
            <p>
              {TRIAL_DAYS_LABEL} бесплатно, без карты и без обязательств. Понравится — продлите на удобный срок.
            </p>
          </div>
          <div className="cta__actions">
            <Button href={`https://t.me/${SITE.botUsername}?start=site`} variant="amber" size="lg" external>
              Попробовать бесплатно
            </Button>
            <Button href="/#pricing" variant="light" size="lg">
              Тарифы
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
