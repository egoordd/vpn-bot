import { cookies } from "next/headers";

import { fetchAdminStats, isValidAdminSession, type AdminStats } from "@/lib/admin";
import { AdminLogin } from "./AdminLogin";
import "./admin.css";

export const dynamic = "force-dynamic";

const TIER_LABELS: Record<string, string> = {
  trial: "Пробные",
  standard: "Обычные",
  premium: "Premium",
  vip: "VIP",
};

function rub(kopecks: number): string {
  return `${Math.round(kopecks / 100).toLocaleString("ru-RU")} ₽`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

export default async function AdminPage() {
  const authed = isValidAdminSession(cookies().get("admin_auth")?.value);
  if (!authed) return <AdminLogin />;

  const stats = await fetchAdminStats();
  if (!stats) {
    return (
      <main className="admin">
        <h1 className="admin__title">Статистика недоступна</h1>
        <p className="admin__muted">
          Не удалось получить данные от API. Проверьте, что заданы переменные ADMIN_API_URL и
          ADMIN_API_TOKEN и что сервис статистики запущен.
        </p>
      </main>
    );
  }

  return <Dashboard stats={stats} />;
}

function Dashboard({ stats }: { stats: AdminStats }) {
  const tiers = Object.entries(stats.subscriptions.activeByTier);
  return (
    <main className="admin">
      <header className="admin__head">
        <h1 className="admin__title">Статистика бота</h1>
        <span className="admin__muted">обновлено {new Date(stats.generatedAt).toLocaleString("ru-RU")}</span>
      </header>

      <section className="admin__cards">
        <Stat label="Пользователей" value={stats.users.total} sub={`+${stats.users.new7d} за неделю`} />
        <Stat label="Активных подписок" value={stats.subscriptions.activeTotal} sub={`всего оформлено: ${stats.subscriptions.total}`} />
        <Stat label="Новых за 24ч" value={stats.users.new24h} />
        <Stat label="Пополнений" value={rub(stats.money.depositsKopecks)} sub={`на балансах: ${rub(stats.money.balancesKopecks)}`} />
      </section>

      <section className="admin__block">
        <h2 className="admin__subtitle">Активные подписки по тарифам</h2>
        <div className="admin__tiers">
          {tiers.length === 0 && <span className="admin__muted">Нет активных подписок</span>}
          {tiers.map(([tier, count]) => (
            <div className="admin__tier" key={tier}>
              <span className="admin__tier-count">{count}</span>
              <span className="admin__tier-label">{TIER_LABELS[tier] ?? tier}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="admin__block">
        <h2 className="admin__subtitle">Последние подписки</h2>
        <div className="admin__table-wrap">
          <table className="admin__table">
            <thead>
              <tr>
                <th>Пользователь</th>
                <th>Тариф</th>
                <th>Оформлена</th>
                <th>До</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {stats.recent.map((row) => (
                <tr key={row.id}>
                  <td>{row.username ? `@${row.username}` : `id ${row.telegramId}`}</td>
                  <td>{row.planTitle}</td>
                  <td>{fmtDate(row.startedAt)}</td>
                  <td>{fmtDate(row.expiresAt)}</td>
                  <td>
                    <span className={`admin__badge admin__badge--${row.isActive ? "on" : "off"}`}>
                      {row.isActive ? "активна" : "истекла"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="admin__card">
      <span className="admin__card-value">{value}</span>
      <span className="admin__card-label">{label}</span>
      {sub && <span className="admin__card-sub">{sub}</span>}
    </div>
  );
}
