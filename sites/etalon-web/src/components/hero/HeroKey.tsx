import { LogoMark } from "@/components/ui/LogoMark";
import "./hero-key.css";

/** Центр первого экрана: золотой ключ-«E»; медленно парит и «поворачивается в замке». */
export function HeroKey() {
  return (
    <div className="herokey" aria-hidden>
      <div className="herokey__halo" />
      <LogoMark className="herokey__mark" />
    </div>
  );
}
