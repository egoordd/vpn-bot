import type { Metadata } from "next";

import { LegalPage } from "@/components/legal/LegalPage";
import { SITE, botLink } from "@/lib/site";
import { PLANS, TRIAL, TRIAL_DAYS_LABEL, pluralDays, pricePerMonth, savingPercent } from "@/lib/tariffs";

export const metadata: Metadata = {
  title: "Тарифы и оплата",
  description: `Тарифы ${SITE.name}: сроки, цены, что входит в подписку и как проходит оплата.`,
};

const TERMS: Record<string, string> = { "1m": "1 месяц", "3m": "3 месяца", "6m": "6 месяцев", "12m": "12 месяцев" };
const DEVICES = PLANS[0].deviceLimit;

export default function TariffsPage() {
  return (
    <LegalPage
      overline="Тарифы"
      title="Тарифы и оплата"
      path="/tariffs/"
      intro={<>Сколько стоит подписка, что в неё входит и как проходит оплата. Цены указаны в рублях и действуют на дату редакции.</>}
    >
      <h2>Стоимость</h2>
      <table className="legal__table">
        <thead>
          <tr>
            <th scope="col">Срок</th>
            <th scope="col">Цена</th>
            <th scope="col">За месяц</th>
          </tr>
        </thead>
        <tbody>
          {PLANS.map((plan) => {
            const saving = savingPercent(plan);
            return (
              <tr key={plan.code}>
                <td>
                  {TERMS[plan.code]} <span className="legal__days">· {pluralDays(plan.durationDays)}</span>
                </td>
                <td>{plan.priceRub.toLocaleString("ru-RU")} ₽</td>
                <td>
                  {pricePerMonth(plan)} ₽{saving > 0 && ` · выгода ${saving}%`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <h2>Что входит в любой тариф</h2>
      <ul>
        <li>доступ ко всем серверам: Польша, Финляндия, Нидерланды, США;</li>
        <li>автоматический выбор самого быстрого сервера;</li>
        <li>режим российских сервисов — банки и Госуслуги работают без отключения VPN;</li>
        <li>до {DEVICES} устройств на одной подписке: iPhone, iPad, Android, Windows, macOS;</li>
        <li>поддержка в Telegram-боте.</li>
      </ul>
      <p>Тарифы отличаются только сроком: чем дольше срок, тем ниже цена за месяц.</p>

      <h2>Как проходит оплата</h2>
      <ul>
        <li>
          откройте бота{" "}
          <a href={botLink()} target="_blank" rel="noopener noreferrer">
            @{SITE.botUsername}
          </a>{" "}
          → «💳 Тарифы» и выберите срок;
        </li>
        <li>оплатите по СБП (QR-код или ссылка из приложения банка) или криптовалютой;</li>
        <li>после подтверждения платежа подписка продлевается на оплаченный срок — ссылка для подключения остаётся прежней.</li>
      </ul>
      <p className="legal__note">
        Оплата разовая: автоматических списаний нет. Перед оплатой бот показывает тариф и итоговую сумму.
      </p>

      <h2>Пробный период</h2>
      <p>
        {TRIAL_DAYS_LABEL} бесплатно, до {TRIAL.deviceLimit} устройств и {TRIAL.trafficGb} ГБ трафика — без оплаты и
        привязки карты. Один раз на аккаунт Telegram.
      </p>

      <h2>Возврат</h2>
      <p>
        Условия возврата — в разделе 7{" "}
        <a href="/terms/#refund">Пользовательского соглашения</a>. Если доступ не заработал по нашей вине, напишите в{" "}
        <a href="/support/">поддержку</a> в течение 24 часов после оплаты.
      </p>
    </LegalPage>
  );
}
