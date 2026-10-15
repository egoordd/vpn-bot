import { SITE, SUPPORT, botLink } from "@/lib/site";
import { TRIAL, TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import { Tower } from "../ui/Tower";
import { Button } from "../ui/ui";
import "./faq.css";

const QUESTIONS = [
  {
    q: "Как получить пробный период?",
    a: `Откройте бота @${SITE.botUsername} и нажмите «🗝 Попробовать». ${TRIAL_DAYS_LABEL} бесплатно, до ${TRIAL.deviceLimit} устройств, без карты. Один пробный период на аккаунт Telegram.`,
  },
  {
    q: "Какие страны доступны?",
    a: "Германия и Нидерланды. Пункт «⚡️ Авто-выбор» в приложении сам держит самый быстрый из них — выбирать вручную не нужно.",
  },
  {
    q: "На каких языках работает бот?",
    a: "Русский, English, Українська, 中文 и فارسی. Язык спрашивается при первом запуске, сменить его можно кнопкой «🌐 Язык» в меню.",
  },
  {
    q: "Сколько устройств можно подключить?",
    a: "На любом тарифе — до 5 устройств: iPhone, iPad, Android, Windows и Mac. Подписка одна, ссылка одна.",
  },
  {
    q: "Что делать, если не подключается?",
    a: `Обновите подписку в Happ (потяните список вниз) и включите VPN заново. Не помогло — напишите в поддержку в боте, ответим в течение ${SUPPORT.replyHours} часов.`,
  },
  {
    q: "Можно ли вернуть деньги?",
    a: "Если доступ не заработал по нашей вине, напишите в поддержку в течение 24 часов после оплаты — условия в разделе 7 пользовательского соглашения.",
  },
] as const;

export function Faq() {
  return (
    <section className="section faq" id="faq" aria-labelledby="faq-title">
      <div className="wrap">
        <div className="section-head">
          <span className="eyebrow">Вопросы</span>
          <h2 id="faq-title">Коротко о главном</h2>
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

export function Gate() {
  return (
    <section className="gate" aria-labelledby="gate-title">
      <div className="wrap">
        <div className="gate__panel">
          <Tower className="gate__tower" />
          <h2 id="gate-title">Ворота открыты</h2>
          <p>{TRIAL_DAYS_LABEL} бесплатно, без карты и обязательств. Понравится — продлите на удобный срок.</p>
          <div className="gate__actions">
            <Button href={botLink("site")} size="lg" external>
              Войти в крепость
            </Button>
            <Button href={SUPPORT.botLink} variant="outline" size="lg" external>
              Задать вопрос
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
