import { BoardingHero } from "@/components/hero/BoardingHero";
import { Departures } from "@/components/board/Departures";
import { OnBoard } from "@/components/onboard/OnBoard";
import { CheckIn } from "@/components/checkin/CheckIn";
import { Tickets } from "@/components/tickets/Tickets";
import { HelpDesk } from "@/components/help/HelpDesk";
import { FinalCall } from "@/components/final/FinalCall";
import { Header } from "@/components/nav/Header";
import { Footer } from "@/components/nav/Footer";

export default function HomePage() {
  return (
    <>
      <Header />
      <main id="main">
        <BoardingHero />
        <Departures />
        <OnBoard />
        <CheckIn />
        <Tickets />
        <HelpDesk />
        <FinalCall />
      </main>
      <Footer />
    </>
  );
}
