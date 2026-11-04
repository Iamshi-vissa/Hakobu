import { HeroBackground } from "@/components/app/HeroBackground";
import { HeroHeadline } from "@/components/app/HeroHeadline";

export function Hero() {
  return (
    <section aria-labelledby="hero-title" className="relative isolate overflow-hidden">
      <HeroBackground />
      <div className="mx-auto max-w-5xl px-4 pt-10 pb-8 text-center sm:pt-16">
        <HeroHeadline />
        <p className="mx-auto mt-5 max-w-2xl text-base text-muted-foreground sm:text-lg">
          Drop in any file — images, documents, spreadsheets, slides, audio, video, e-books or archives. Hakobu
          reads what it really is and shows only the formats it can become.
        </p>
      </div>
    </section>
  );
}
