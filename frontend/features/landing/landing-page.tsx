import { Navigation } from "./navigation";
import { ResearchPreview } from "./research-preview";
import { Brand, Icon } from "./icons";

import { Button } from "@/components/ui/button";
import { siteConfig } from "@/config/site";

const repository = siteConfig.repoUrl;

export function LandingPage() {
  return (
    <div className="qtm-landing">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div id="top">
        <Navigation />
      </div>
      <main id="main">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-ambient" aria-hidden="true" />
          <div className="hero-content shell">
            <p className="hero-badge">
              <span className="status-dot" /> A NEW PERSPECTIVE ON THE PAST
            </p>
            <h1 id="hero-title">
              LOOK BACK.
              <br />
              <span>THINK FORWARD.</span>
            </h1>
            <p className="hero-description">
              Meet <strong>Quant Time Machine.</strong> Explore markets as they
              were,
              <br className="desktop-break" /> test your ideas, and leave
              look-ahead bias behind.
            </p>
            <div className="hero-actions">
              <Button asChild className="button button-primary">
                <a href="#research">
                  Explore the time machine <Icon name="diagonal" />
                </a>
              </Button>
              <a href="#how-it-works" className="text-link">
                <span className="play-icon">
                  <Icon name="play" />
                </span>
                See how it works
              </a>
            </div>
            <p className="hero-footnote">
              BUILT FOR CURIOSITY. GROUNDED IN DATA.
            </p>
          </div>
          <div className="horizon-scene" aria-hidden="true">
            <div className="horizon-glow" />
            <div className="horizon-arc" />
            <div className="horizon-grid" />
            <span className="horizon-coordinate coordinate-left">
              [ TIME MODEL / AS-OF ]
            </span>
            <span className="horizon-coordinate coordinate-right">
              PAST → POSSIBILITY
            </span>
          </div>
          <div className="hero-bottom shell">
            <span>
              <i /> POINT-IN-TIME RESEARCH. BUILT ON CONTEXT.
            </span>
            <a href="#platform">
              SCROLL TO EXPLORE <span>↓</span>
            </a>
          </div>
        </section>

        <section className="source-strip" aria-label="Research data sources">
          <div className="shell source-strip-inner">
            <span className="source-intro">
              A clearer picture.
              <br />
              <strong>From the source.</strong>
            </span>
            <span className="source-logo sec">
              <span className="source-symbol">◉</span> SEC <small>EDGAR</small>
            </span>
            <span className="source-divider">+</span>
            <span className="source-logo fred">
              <svg viewBox="0 0 28 24" aria-hidden="true">
                <path
                  d="M1 20h26M3 17l5-7 5 3 5-10 7 4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                />
              </svg>{" "}
              FRED<span className="registered">®</span>
            </span>
            <span className="source-divider">+</span>
            <span className="source-logo tiingo">
              <span className="tiingo-symbol">▥</span> tiingo
            </span>
            <span className="source-strip-note">
              PRICES. FILINGS. FUNDAMENTALS.
              <br />
              ONE POINT IN TIME.
            </span>
          </div>
        </section>

        <section
          className="platform-section shell section-space"
          id="platform"
          aria-labelledby="platform-title"
        >
          <div className="section-heading">
            <div>
              <p className="eyebrow">
                <span className="section-number">01 /</span> YOUR RESEARCH,
                REIMAGINED
              </p>
              <h2 id="platform-title">
                Hindsight is powerful.
                <br />
                <span>Use it honestly.</span>
              </h2>
            </div>
            <p>
              A backtest is only as good as the information behind it. We’re
              building a research environment that puts every data point back in
              its own time.
            </p>
          </div>
          <div className="feature-grid">
            {[
              {
                number: "01",
                icon: "clock" as const,
                title: "The past. As it was.",
                text: "Reconstruct what was actually known at a historical date. No future filings. No revised numbers sneaking in.",
                tag: "POINT-IN-TIME DATA",
              },
              {
                number: "02",
                icon: "chart" as const,
                title: "Ideas meet evidence.",
                text: "Turn a market hypothesis into a structured experiment, with a deterministic backtesting engine at its core.",
                tag: "REPRODUCIBLE BACKTESTS",
              },
              {
                number: "03",
                icon: "layers" as const,
                title: "Every number, a story.",
                text: "Trace a fact to its source and publication date. Understand what went into your research, and why.",
                tag: "TRANSPARENT PROVENANCE",
              },
            ].map((feature) => (
              <article className="feature" key={feature.number}>
                <div className="feature-top">
                  <Icon name={feature.icon} />
                  <span>{feature.number}</span>
                </div>
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
                <span className="feature-tag">
                  <i />
                  {feature.tag}
                </span>
              </article>
            ))}
          </div>
        </section>

        <section
          className="research-section section-space"
          id="research"
          aria-labelledby="research-title"
        >
          <div className="shell">
            <div className="section-heading">
              <div>
                <p className="eyebrow">
                  <span className="section-number">02 /</span> GO BACK. GET
                  AHEAD.
                </p>
                <h2 id="research-title">
                  A little less guesswork.
                  <br />
                  <span>A lot more perspective.</span>
                </h2>
              </div>
              <div className="section-aside">
                <span className="outline-badge">
                  <span className="status-dot" /> THE INTERACTIVE PREVIEW
                </span>
                <p>
                  Take a first look at the research experience.
                  <br />
                  Pick a strategy. Choose a moment. Explore.
                </p>
              </div>
            </div>
            <ResearchPreview />
          </div>
        </section>

        <section
          className="workflow-section shell section-space"
          id="how-it-works"
          aria-labelledby="workflow-title"
        >
          <div className="workflow-intro">
            <p className="eyebrow">
              <span className="section-number">03 /</span> FROM WHAT IF TO WHAT
              WAS
            </p>
            <h2 id="workflow-title">
              Good questions.
              <br />
              <span>Better foundations.</span>
            </h2>
            <p>
              A deliberate path from your first hypothesis to research you can
              retrace.
            </p>
            <a href="#research" className="text-link">
              Try the interactive preview <Icon name="arrow" />
            </a>
            <div className="time-orbit" aria-hidden="true">
              <div />
              <div />
              <Icon name="clock" />
              <span>PAST → PERSPECTIVE</span>
            </div>
          </div>
          <div className="workflow-steps">
            {[
              [
                "Set the clock.",
                "Choose your historical cutoff. Start with the information available at that moment, before hindsight changes the picture.",
              ],
              [
                "Build the hypothesis.",
                "Define the question, the universe, and the rules. Give your idea a clear, repeatable structure.",
              ],
              [
                "Follow the evidence.",
                "Compare outcomes, inspect the assumptions, and trace the data. Keep the research reproducible from the start.",
              ],
            ].map(([title, text], index) => (
              <article key={title}>
                <span className="step-number">0{index + 1}</span>
                <div>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </div>
                <Icon name="diagonal" />
              </article>
            ))}
          </div>
        </section>

        <section
          className="data-section shell"
          id="data-sources"
          aria-labelledby="data-title"
        >
          <div className="data-copy">
            <p className="eyebrow">
              <span className="section-number">04 /</span> CONTEXT IS EVERYTHING
            </p>
            <h2 id="data-title">
              Real sources.
              <br />
              <span>Clear origins.</span>
            </h2>
            <p>
              Our data layer is being built around historical prices, published
              company information, and vintage economic releases. Each has its
              own clock. We respect that.
            </p>
            <a
              href={`${repository}/blob/main/doc/data-sources.md`}
              className="text-link"
              target="_blank"
              rel="noopener noreferrer"
            >
              Read our data approach <Icon name="diagonal" />
            </a>
          </div>
          <div className="data-list">
            <div>
              <span className="data-source-name">
                01 <strong>Tiingo</strong>
              </span>
              <span>Daily market prices</span>
              <Icon name="chart" />
            </div>
            <div>
              <span className="data-source-name">
                02 <strong>SEC EDGAR</strong>
              </span>
              <span>Filings & fundamentals</span>
              <Icon name="layers" />
            </div>
            <div>
              <span className="data-source-name">
                03 <strong>FRED / ALFRED</strong>
              </span>
              <span>Vintage economic data</span>
              <Icon name="clock" />
            </div>
            <p>
              Source availability and historical coverage vary. See our data
              documentation for details.
            </p>
          </div>
        </section>

        <section className="closing-section shell">
          <p className="eyebrow">
            <span className="status-dot" /> CURIOSITY DOESN’T NEED A CRYSTAL
            BALL
          </p>
          <h2>
            Your next idea.
            <br />
            <span>A different point in time.</span>
          </h2>
          <Button asChild className="button button-primary">
            <a href="#research">
              Explore the time machine <Icon name="diagonal" />
            </a>
          </Button>
          <span className="closing-coordinate" aria-hidden="true">
            [ PAST → POSSIBILITY ]
          </span>
        </section>
      </main>
      <footer className="site-footer shell">
        <div className="footer-top">
          <Brand />
          <span>
            A research platform in development.
            <br />
            Built by the Quant Time Machine team.
          </span>
          <a href={repository} target="_blank" rel="noopener noreferrer">
            <Icon name="github" /> Follow the project <Icon name="diagonal" />
          </a>
        </div>
        <div className="footer-bottom">
          <span>© 2026 Quant Time Machine</span>
          <span>Research with perspective.</span>
          <a href="#top">Back to top ↑</a>
        </div>
        <p className="source-attribution">
          {siteConfig.disclaimer}
          This product uses the FRED® API but is not endorsed or certified by
          the Federal Reserve Bank of St. Louis.{" "}
          <a
            href="https://fred.stlouisfed.org/docs/api/terms_of_use.html"
            target="_blank"
            rel="noopener noreferrer"
          >
            FRED API Terms of Use
          </a>
          .
        </p>
      </footer>
    </div>
  );
}
