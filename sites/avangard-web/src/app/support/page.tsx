import type { Metadata } from "next";

import { LegalPage } from "@/components/legal/LegalPage";
import { Button } from "@/components/ui/ui";
import { SITE, SUPPORT } from "@/lib/site";

export const metadata: Metadata = {
  title: "Поддержка",
  description: `Как связаться с поддержкой ${SITE.name}: обращения в Telegram-боте, срок ответа.`,
};

export default function SupportPage() {
  return (
    <LegalPage
      overline="Контакты"
      title="Поддержка"
      path="/support/"
      intro={<>Отвечаем на вопросы о подключении, оплате и возврате. Обращение — прямо в Telegram-боте, ответ придёт туда же.</>}
    >
      <h2>Как написать</h2>
      <ul>
        <li>
          откройте бота{" "}
          <a href={SUPPORT.botLink} target="_blank" rel="noopener noreferrer">
            @{SITE.botUsername}
          </a>{" "}
          и нажмите «💬 Поддержка»;
        </li>
        <li>опишите вопрос одним или несколькими сообщениями, можно приложить скриншот;</li>
        <li>сообщение получит администрация сервиса, ответ придёт в этот же чат.</li>
      </ul>
      <p>
        <Button href={SUPPORT.botLink} variant="outline" external>
          Написать в поддержку
        </Button>
      </p>
      {SUPPORT.email && (
        <p>
          Почта: <a href={`mailto:${SUPPORT.email}`}>{SUPPORT.email}</a>
        </p>
      )}

      <h2>Срок ответа</h2>
      <p className="legal__note">
        Обычно — в течение нескольких часов, не позднее {SUPPORT.replyHours} часов с момента обращения.
      </p>

      <h2>Что указать в обращении</h2>
      <ul>
        <li>устройство и приложение, на котором не работает подключение;</li>
        <li>по вопросам оплаты и возврата — дату, сумму и способ оплаты;</li>
        <li>скриншот ошибки, если она есть.</li>
      </ul>

      <h2>Документы</h2>
      <p>
        <a href="/tariffs/">Тарифы и оплата</a> · <a href="/terms/">Пользовательское соглашение</a> ·{" "}
        <a href="/privacy/">Политика конфиденциальности</a>
      </p>
    </LegalPage>
  );
}
