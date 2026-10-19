// Site-wide constants: names, links, and required notices.

export const siteConfig = {
  name: "Quant Time Machine",
  description: "Point-in-time research and backtesting without look-ahead bias.",
  tagline:
    "Test investment ideas using only the information that was actually available on each historical date.",
  course: "CISC 498/499 capstone · University of Delaware",
  repoUrl: "https://github.com/nfiasco/Quant-Time-Machine",
  roadmapUrl:
    "https://github.com/nfiasco/Quant-Time-Machine/blob/main/doc/roadmap.md",
  timeModelUrl:
    "https://github.com/nfiasco/Quant-Time-Machine/blob/main/doc/time-model.md",
  disclaimer: "For research and education. Not investment advice.",
  // Required by the FRED API terms of use wherever FRED data appears.
  fredNotice:
    "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.",
} as const;
