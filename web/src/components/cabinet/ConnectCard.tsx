import { CopyButton } from "@/components/ui/CopyButton";
import "./connect-card.css";

const APPS = [
  { name: "Happ", scheme: (url: string) => `happ://add/${encodeURIComponent(url)}` },
  { name: "V2RayTun", scheme: (url: string) => `v2raytun://import/${encodeURIComponent(url)}` },
  { name: "Hiddify", scheme: (url: string) => `hiddify://import/${encodeURIComponent(url)}` },
];

export function ConnectCard({
  subscriptionUrl,
  qrDataUrl = null,
}: {
  subscriptionUrl: string | null;
  qrDataUrl?: string | null;
}) {
  if (!subscriptionUrl) {
    return (
      <article className="card card--span2 connect">
        <div className="card__head">
          <span className="card__title">Подключение устройств</span>
        </div>
        <p className="connect__empty">
          Ссылка-подписка появится здесь после активации тарифа.
        </p>
      </article>
    );
  }

  return (
    <article className="card card--span2 connect">
      <div className="card__head">
        <span className="card__title">Подключение устройств</span>
      </div>

      <p className="connect__lead">
        Импортируйте ссылку в приложение — конфиг обновляется автоматически.
      </p>

      <div className="connect__link">
        <code className="connect__url mono">{subscriptionUrl}</code>
        <CopyButton value={subscriptionUrl} label="Скопировать ссылку" />
      </div>

      <div className="connect__apps">
        <span className="connect__apps-label mono">Открыть в:</span>
        {APPS.map((app) => (
          <a key={app.name} className="connect__app" href={app.scheme(subscriptionUrl)}>
            {app.name}
          </a>
        ))}
      </div>

      {qrDataUrl && (
        <figure className="connect__qr">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={qrDataUrl} alt="QR-код ссылки-подписки" width={180} height={180} />
          <figcaption className="mono">Сканируйте с телефона</figcaption>
        </figure>
      )}
    </article>
  );
}
