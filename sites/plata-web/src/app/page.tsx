import { Connect } from "@/components/connect/Connect";
import { Cta, Faq } from "@/components/faq/Faq";
import { Hero } from "@/components/hero/Hero";
import { Levels } from "@/components/levels/Levels";
import { Footer, Header } from "@/components/nav/Nav";
import { Pricing } from "@/components/pricing/Pricing";

export default function HomePage() {
  return (
    <>
      <Header />
      <main id="main">
        <Hero />
        <Levels />
        <Connect />
        <Pricing />
        <Faq />
        <Cta />
      </main>
      <Footer />
    </>
  );
}
