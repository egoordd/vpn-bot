import { Hero } from "@/components/hero/Hero";
import { Stats } from "@/components/stats/Stats";
import { Features } from "@/components/features/Features";
import { Connect } from "@/components/connect/Connect";
import { Pricing } from "@/components/pricing/Pricing";
import { Faq } from "@/components/faq/Faq";
import { Cta } from "@/components/cta/Cta";
import { Header } from "@/components/nav/Header";
import { Footer } from "@/components/nav/Footer";

export default function HomePage() {
  return (
    <>
      <Header />
      <main id="main">
        <Hero />
        <Stats />
        <Features />
        <Connect />
        <Pricing />
        <Faq />
        <Cta />
      </main>
      <Footer />
    </>
  );
}
