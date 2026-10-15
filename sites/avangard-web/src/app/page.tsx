import { Faq, Gate } from "@/components/faq/Faq";
import { Hero } from "@/components/hero/Hero";
import { Footer, Header } from "@/components/nav/Nav";
import { Peek } from "@/components/peek/Peek";
import { Pricing } from "@/components/pricing/Pricing";
import { Towers } from "@/components/towers/Towers";
import { Walls } from "@/components/walls/Walls";

export default function HomePage() {
  return (
    <>
      <Header />
      <main id="main">
        <Hero />
        <Peek />
        <Walls />
        <Towers />
        <Pricing />
        <Faq />
        <Gate />
      </main>
      <Footer />
    </>
  );
}
