import { LogoMark } from "@/components/ui/LogoMark";
import "./hero-lock.css";

/** Hero centrepiece: the brand twin-U lock; its shackle clicks open on a loop. */
export function HeroLock() {
  return (
    <div className="herolock" aria-hidden>
      <LogoMark className="herolock__mark" />
    </div>
  );
}
