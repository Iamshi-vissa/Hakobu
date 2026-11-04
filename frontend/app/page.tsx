import { Converter } from "@/components/app/Converter";
import { Hero } from "@/components/app/Hero";
import { SiteHeader } from "@/components/app/SiteHeader";

export default function Home() {
  return (
    <>
      <a
        href="#converter"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        Skip to converter
      </a>
      <SiteHeader />
      <main>
        <Hero />
        <Converter />
      </main>
      <footer className="mx-auto max-w-5xl px-4 py-10 text-center text-sm text-muted-foreground">
        Files are processed on our servers and deleted automatically after one hour. Hakobu (運ぶ) means “to carry”.
      </footer>
    </>
  );
}
