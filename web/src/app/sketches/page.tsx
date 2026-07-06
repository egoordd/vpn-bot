import "./sketches.css";

/** Preview (NOT linked) at /sketches — twin-U lock logo system per the reference. */
export default function SketchesPage() {
  return (
    <main className="sk-page">
      <header className="sk-head">
        <h1>UnLock — знак из двух «U»</h1>
        <p>Капсула-замок с буквой U внутри. В слове VPN буква V заменена на U → UPN.</p>
      </header>

      <section className="sk-grid">
        <article className="sk-card">
          <div className="sk-stage"><Mark /></div>
          <h3>1 · Замок закрыт</h3>
        </article>
        <article className="sk-card">
          <div className="sk-stage"><Mark open /></div>
          <h3>2 · Замок открыт</h3>
        </article>
        <article className="sk-card">
          <div className="sk-stage sk-stage--dark">
            <div className="tile"><Mark className="mark--cream" /></div>
          </div>
          <h3>3 · Тайл (иконка бота)</h3>
        </article>

        <article className="sk-card" style={{ gridColumn: "1 / -1" }}>
          <div className="sk-stage sk-stage--wide">
            <Wordmark />
          </div>
          <h3>Вордмарк · светлый</h3>
        </article>
        <article className="sk-card" style={{ gridColumn: "1 / -1" }}>
          <div className="sk-stage sk-stage--wide sk-stage--dark">
            <Wordmark cream />
          </div>
          <h3>Вордмарк · тёмный</h3>
        </article>
      </section>
    </main>
  );
}

/** Twin-U padlock: capsule outline (shackle = top arch, body = sides+bottom)
 * with a bold U nested inside. `open` lifts the top-right shackle cap. */
function Mark({ open = false, className = "" }: { open?: boolean; className?: string }) {
  return (
    <svg viewBox="0 0 100 132" className={`mark ${className}`} role="img" aria-label="UnLock">
      <path className="lk lk-outer" d="M50 10 A26 26 0 0 0 24 36 L24 96 A26 26 0 0 0 76 96 L76 36" />
      <path
        className="lk lk-cap"
        d="M76 36 A26 26 0 0 0 50 10"
        style={
          open
            ? { transformBox: "view-box", transformOrigin: "76px 36px", transform: "translate(6px,-10px) rotate(12deg)" }
            : undefined
        }
      />
      <path className="lk lk-u" d="M38 60 L38 82 A12 12 0 0 0 62 82 L62 60" />
    </svg>
  );
}

function Wordmark({ cream = false }: { cream?: boolean }) {
  return (
    <span className={`wm${cream ? " wm--cream" : ""}`}>
      <svg viewBox="0 0 100 132" className="wm__mark lk-wrap" aria-hidden>
        <path className="lk lk-outer" d="M50 10 A26 26 0 0 0 24 36 L24 96 A26 26 0 0 0 76 96 L76 36" />
        <path className="lk lk-cap" d="M76 36 A26 26 0 0 0 50 10" />
        <path className="lk lk-u" d="M38 60 L38 82 A12 12 0 0 0 62 82 L62 60" />
      </svg>
      nlock<span className="wm__upn">UPN</span>
    </span>
  );
}
