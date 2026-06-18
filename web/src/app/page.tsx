import { CtaBanner } from "@/components/cta/CtaBanner";
import { Faq } from "@/components/faq/Faq";
import { Features } from "@/components/features/Features";
import { Hero } from "@/components/hero/Hero";
import { HowItWorks } from "@/components/how/HowItWorks";
import { SiteFooter } from "@/components/nav/SiteFooter";
import { SiteNav } from "@/components/nav/SiteNav";
import { Pricing } from "@/components/pricing/Pricing";
import { TrustBar } from "@/components/trust/TrustBar";
import { Locations } from "@/components/world/Locations";

export default function HomePage() {
  return (
    <>
      <SiteNav />
      <main id="main">
        <Hero />
        <TrustBar />
        <Locations />
        <Features />
        <HowItWorks />
        <Pricing />
        <Faq />
        <CtaBanner />
      </main>
      <SiteFooter />
    </>
  );
}
