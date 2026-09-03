import type { ReactNode } from "react";
import Header from "./Header";
import HealthProvider from "./HealthProvider";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <HealthProvider>
      <div className="flex min-h-screen flex-col">
        <Header />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-16 pt-8 sm:px-6 sm:pt-12">{children}</main>
        <footer className="border-t border-paper-line/70">
          <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-ink-mute sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p>
              Glimpse is open source under the MIT license.{" "}
              <a
                className="underline decoration-paper-line underline-offset-2 hover:text-ink"
                href="https://github.com/daviskeene/glimpse"
                target="_blank"
                rel="noopener noreferrer"
              >
                Source, issues and the security model are on GitHub.
              </a>
            </p>
            <p className="font-mono">
              built by{" "}
              <a className="hover:text-ink" href="https://daviskeene.com" target="_blank" rel="noopener noreferrer">
                Davis Keene
              </a>
            </p>
          </div>
        </footer>
      </div>
    </HealthProvider>
  );
}
