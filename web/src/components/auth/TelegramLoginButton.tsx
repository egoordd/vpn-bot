import "./telegram-login.css";

interface TelegramLoginButtonProps {
  /** Built server-side by telegramLoginUrl(); null when the bot token is unset. */
  href: string | null;
}

/**
 * Sign in with Telegram, as a plain link.
 *
 * This used to be Telegram's official widget, which injects a script from
 * telegram.org and builds its button inside an iframe. That script evaluates
 * strings as code, so our Content-Security-Policy blocked it and the button
 * silently never appeared — the page just showed "или" followed by nothing.
 * The fix is not to allow 'unsafe-eval' site-wide for one button: Telegram's
 * redirect flow carries the same signed payload and needs no third-party
 * script, so the policy got tighter instead of looser.
 */
export function TelegramLoginButton({ href }: TelegramLoginButtonProps) {
  if (!href) return null;
  return (
    <a className="tglogin" href={href}>
      <svg className="tglogin__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path
          fill="currentColor"
          d="M21.9 4.3 18.6 20c-.2.9-.7 1.1-1.5.7l-4.1-3-2 1.9c-.2.2-.4.4-.9.4l.3-4.2 7.6-6.9c.3-.3-.1-.4-.5-.2l-9.4 5.9-4-1.3c-.9-.3-.9-.9.2-1.3l15.7-6c.7-.3 1.4.2 1.1 1.3Z"
        />
      </svg>
      Войти через Telegram
    </a>
  );
}
